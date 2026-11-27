# ============================================================
# 智巡 AI 识别中心 —— FastAPI 薄后端
# ------------------------------------------------------------
# POST /api/recognize  接收图片 → 调多模态大模型识别 → 结构化结果
# GET  /api/health     健康检查（含模型配置状态）
#
# 模型接入：OpenAI 兼容接口（base_url / api_key / model 均在
#           server/config.local.json 配置，该文件不进代码库）
# 依赖：fastapi uvicorn httpx python-multipart（uv 管理）
# ============================================================
import base64
import json
import re
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.responses import Response

from report_pdf import build_report_pdf

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.local.json"

# ---------- 配置加载（本地文件，不进代码库） ----------
def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

CFG = load_config()

app = FastAPI(title="智巡 AI 识别服务", version="1.0")

# 本地开发跨域（vite dev 5199 / preview 4173 / GitHub Pages 在线演示）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://localhost:5199", "http://127.0.0.1:5199",
        "http://localhost:4173", "http://127.0.0.1:4173",   # vite preview（生产包冒烟）
        "https://lee-q-w.github.io",                        # 在线演示：评审本地起后端即可用 AI/PDF 全功能
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- 识别提示词 ----------
SYSTEM_PROMPT = """你是园区/仓储智能巡检系统的视觉识别模块。分析照片，判断是否存在以下类型的异常：
- cigarette 未熄烟头
- dry 植被缺水（草坪/植物发黄干枯斑块）
- litter 垃圾分类违规（垃圾桶旁散落杂物、垃圾未入桶）
- goods 货物堆放违规（货物越线、占道堆放）
- blocked 通道占用（安全出口/疏散通道被堵）
- waterlogging 积水内涝（路面积水成片、下凹处积水、井盖顶起或旋涡）
注意：摆放在路侧/路边的交通锥、施工围挡属于园区正常设施，不构成异常；仅当安全出口、疏散通道或消防通道被实际堵塞时才判 blocked。
雨天注意：湿地面反光、水渍、倒影常被误判为垃圾或油污，只有确认存在实体杂物时才判 litter；积水要区分正常雨水湿滑与成片积水（能形成镜面反光、边界清晰、淹及路面标线才算 waterlogging）。
描述 evidence 时只描述画面中的场景实体（地面、草坪、道路、垃圾、烟头等），忽略画面角落的水印、OSD、时间戳等文字标记，不要在描述中出现"模拟/mock/SIM"等字样。

严格只输出 JSON，不要任何其他文字。格式：
{"found": true/false, "type": "类型代码或 null", "label": "异常中文名或 null", "confidence": 0到1的小数, "evidence": "画面中看到的具体描述（中文，1-2句）"}
若照片中没有任何上述异常，found 为 false，其余字段为 null。"""

TYPE_ALIASES = {
    "cigarette": ["烟头", "未熄烟头", "香烟", "烟蒂"],
    "dry": ["缺水", "植被缺水", "干枯", "发黄", "枯黄"],
    "litter": ["垃圾", "垃圾分类", "杂物", "散落"],
    "goods": ["货物", "堆放", "越线", "占道"],
    "blocked": ["通道", "占用", "堵塞", "安全出口", "疏散"],
    "waterlogging": ["积水", "内涝", "水浸", "涝", "漫水"],
}


def _sanitize_evidence(text: str) -> str:
    """净化证据描述：剥离模型从帧水印带入的 mock/SIM 字样（成片证据需干净）"""
    if not text:
        return text
    t = text
    t = re.sub(r"[（(]\s*(?:mock|sim|模拟)\s*[)）]", "", t, flags=re.I)
    t = re.sub(r"(?i)\bmock\b", "", t)
    t = re.sub(r"(?i)sim\s*device", "", t)
    t = re.sub(r"模拟摄像头帧", "", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" ，,。.；;-—")
    return t


def parse_model_output(text: str) -> dict:
    """从模型回复中稳健提取 JSON（容忍 ```json 包裹或前后杂讯）"""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {"found": False, "type": None, "label": None, "confidence": 0, "evidence": "模型输出无法解析"}
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"found": False, "type": None, "label": None, "confidence": 0, "evidence": "模型输出无法解析"}
    # 规范化
    found = bool(obj.get("found"))
    ctype = obj.get("type")
    if isinstance(ctype, str) and ctype not in TYPE_ALIASES:
        # 中文类型名 → 代码
        for code, aliases in TYPE_ALIASES.items():
            if any(a in ctype for a in aliases):
                ctype = code
                break
    conf = obj.get("confidence")
    try:
        conf = float(conf)
        if conf > 1.5:          # 明显是百分数（如 88、97）
            conf = conf / 100.0
        conf = max(0.0, min(1.0, conf))
    except (TypeError, ValueError):
        conf = 0.5
    return {
        "found": found,
        "type": ctype if found else None,
        "label": obj.get("label") if found else None,
        "confidence": round(conf, 2) if found else 0,
        "evidence": _sanitize_evidence((obj.get("evidence") or "").strip()) or "模型未提供描述",
    }


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "model_configured": bool(CFG.get("api_key") and CFG.get("base_url")),
        "model": CFG.get("model", ""),
    }


# ---------- 模型配置（评审/使用者在页面里填自己的 Key，开箱即用） ----------
def _mask_key(k: str) -> str:
    """Key 掩码回显：只露首尾，不回传完整密钥"""
    if not k:
        return ""
    if len(k) <= 8:
        return k[:2] + "****"
    return k[:4] + "****" + k[-4:]


@app.get("/api/config/model")
async def get_model_config():
    return {
        "configured": bool(CFG.get("api_key") and CFG.get("base_url")),
        "baseUrl": CFG.get("base_url", ""),
        "model": CFG.get("model", ""),
        "apiKeyMasked": _mask_key(CFG.get("api_key", "")),
    }


@app.post("/api/config/model")
async def save_model_config(data: dict):
    """保存模型配置并写入 config.local.json（不进代码库）；test=True 时顺带试连验证"""
    global CFG
    base_url = str(data.get("baseUrl") or "").strip().rstrip("/")
    api_key = str(data.get("apiKey") or "").strip()
    model = str(data.get("model") or "").strip()
    if not base_url.startswith(("http://", "https://")):
        raise HTTPException(400, "base_url 需以 http:// 或 https:// 开头")
    if not model:
        raise HTTPException(400, "model 不能为空（如 gpt-4o-mini / qwen-vl-plus）")
    if not api_key and not CFG.get("api_key"):
        raise HTTPException(400, "apiKey 不能为空")

    # 编辑模式 key 留空 = 沿用已保存的 Key
    merged = dict(CFG)
    merged.update({"base_url": base_url, "model": model})
    if api_key:
        merged["api_key"] = api_key

    # 试连验证（保存前先测，失败不落盘，避免坏配置覆盖可用配置）
    test_ok, test_err = await _test_model(merged)
    if not test_ok and data.get("strict", True):
        raise HTTPException(400, f"试连失败：{test_err}")

    # 写本地文件（保留 port 等其他字段）
    try:
        CONFIG_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        raise HTTPException(500, f"配置文件写入失败：{e}")
    CFG = merged
    return {
        "ok": True, "testOk": test_ok, "testError": test_err,
        "configured": True, "apiKeyMasked": _mask_key(CFG.get("api_key", "")),
    }


async def _test_model(cfg: dict) -> tuple:
    """用最小请求试连模型服务（验证 base_url/key/model 三元组可用）"""
    payload = {
        "model": cfg.get("model", ""),
        "messages": [{"role": "user", "content": "回复OK"}],
        "max_tokens": 10,
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{cfg['base_url'].rstrip('/')}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {cfg['api_key']}"},
            )
            if r.status_code == 200:
                return True, ""
            detail = ""
            try:
                detail = r.json().get("error", {}).get("message", "")[:150]
            except Exception:  # noqa: BLE001
                detail = r.text[:150]
            return False, f"模型服务返回 {r.status_code}" + (f"：{detail}" if detail else "")
    except httpx.TimeoutException:
        return False, "连接超时（15s），请检查 base_url 是否可达"
    except httpx.HTTPError as e:
        return False, f"连接失败：{e}"


@app.post("/api/recognize")
async def recognize(file: UploadFile = File(...)):
    if not (CFG.get("api_key") and CFG.get("base_url")):
        raise HTTPException(503, "模型未配置：请在 server/config.local.json 填写 base_url / api_key / model（参考 config.example.json）")

    data = await file.read()
    if not data:
        raise HTTPException(400, "空文件")
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(413, "图片超过 8MB 上限")
    b64 = base64.b64encode(data).decode()

    payload = {
        "model": CFG.get("model", "agnes-3.0-flash"),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请识别这张巡检照片中的异常。"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                ],
            },
        ],
        "temperature": 0.1,
        "max_tokens": 2000,
    }
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(
                f"{CFG['base_url'].rstrip('/')}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {CFG['api_key']}"},
            )
            r.raise_for_status()
            body = r.json()
    except httpx.TimeoutException:
        raise HTTPException(504, "模型调用超时（90s）")
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"模型服务返回错误 {e.response.status_code}：{e.response.text[:200]}")
    except httpx.HTTPError as e:
        raise HTTPException(502, f"模型服务连接失败：{e}")

    content = ""
    try:
        msg = body["choices"][0]["message"]
        content = msg.get("content") or ""
        if isinstance(content, list):  # 兼容多模态分段输出
            content = "".join(seg.get("text", "") for seg in content if isinstance(seg, dict))
        # 推理型模型：content 为空（token 预算被推理耗尽）时，从 reasoning_content 兑底提取 JSON
        if not content.strip():
            rc = msg.get("reasoning_content") or ""
            if isinstance(rc, str) and rc.strip():
                content = rc
    except (KeyError, IndexError, TypeError):
        raise HTTPException(502, "模型响应格式异常")

    result = parse_model_output(content)
    result["raw"] = content[:500]
    return result


# ---------- 巡检报告导出（PDF，reportlab，无需模型 key） ----------
@app.post("/api/report/export")
async def export_report(data: dict):
    findings = data.get("findings") or []
    if not isinstance(findings, list) or len(findings) > 50:
        raise HTTPException(400, "findings 必须为列表（≤50 条）")
    for f in findings:
        for k in ("photoB64", "droneB64"):
            v = f.get(k)
            if v and (not isinstance(v, str) or len(v) > 4 * 1024 * 1024):
                raise HTTPException(400, f"照片 {k} 数据过大（≤4MB base64）")
    try:
        pdf = build_report_pdf(data)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"PDF 生成失败：{e}")
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="smartpatrol-report-{ts}.pdf"'},
    )


import knowledge_base as kb  # 本地 RAG：巡检知识库检索（零依赖 BM25）

# ---------- AI 巡检助手（自然语言 → 意图 → 平台动作） ----------
AGENT_SYSTEM_PROMPT = """你是"智巡"智能巡检平台的语音助手"小巡"。用户（园区管理员，非技术人员）用自然语言指挥平台，你负责理解意图并产出动作。

当前平台状态：
{context_block}

可执行动作（actions 数组，按需 0 个或多个）：
- {{"type":"patrol","args":{{"zoneIds":["zone-c"],"mode":"point"}}}}  发起巡逻。zoneIds 省略=全部分区；mode：quick 快速巡逻/point 定点详查/sweep 环视检查，省略=保持当前方式
- {{"type":"switch_mode","args":{{"mode":"real"}}}}  切换数据源。sim 仿真/replay 历史回放/real 真机
- {{"type":"switch_scene","args":{{"sceneId":"warehouse"}}}}  切换巡检场景
- {{"type":"export_report","args":{{}}}}  导出 PDF 巡检报告
- {{"type":"mark_resolved","args":{{"all":true}}}}  标记异常处置完成
- {{"type":"recheck","args":{{"all":true}}}}  无人机复核全部待复核异常

规则：
1. 严格只输出 JSON（不要 markdown 包裹）：{{"reply":"简短中文回复，1-2 句，口语化，说明做了什么或结果如何","actions":[...]}}
2. 任务进行中（phase 不为 idle/report）时不发起 patrol，回复请用户稍候
3. 查询类问题（"有什么异常/情况怎么样"）直接依据状态信息回答，actions 为空数组
4. 处置方法、规范、平台用法类问题，优先依据知识库参考资料回答，保持简短；与参考资料无关的平台状态问题仍依据状态信息
5. 不确定意图时友好追问，不做猜测动作
6. 雨天约束：作业环境为大雨时不要输出 recheck 动作（无人机无法起飞），改为建议人工确认；植被缺水类异常建议雨停后再处置；被问"雨天怎么巡检/器械还要不要"时，依据知识库与约束如实说明降级项（无人机停飞、车只跑关键点、固定摄像头与人工补位）

知识库参考资料（来自本地巡检知识库检索，与问题相关时可引用）：
{knowledge_block}"""


def _build_context_block(ctx: dict) -> str:
    """把前端上报的运行状态整理成紧凑的中文上下文"""
    lines = []
    scenes = ", ".join(f"{s.get('id')}={s.get('name')}" for s in ctx.get("scenes") or [])
    if scenes:
        lines.append(f"可选场景：{scenes}")
    lines.append(f"当前场景：{ctx.get('sceneName', '—')}（{ctx.get('sceneId', '—')}）")
    zones = ", ".join(f"{z.get('id')}={z.get('name')}" for z in ctx.get("zones") or [])
    if zones:
        lines.append(f"当前场景分区：{zones}")
    mode_names = {"sim": "仿真模式", "replay": "回放模式", "real": "真机模式"}
    lines.append(f"数据源：{mode_names.get(ctx.get('mode'), ctx.get('mode', '—'))}")
    phase_names = {"idle": "待命（可发起任务）", "patrol": "巡逻中", "detect": "识别异常中",
                   "recheck": "无人机复核中", "report": "已完成（可发起任务）"}
    lines.append(f"任务阶段：{phase_names.get(ctx.get('phase'), ctx.get('phase', '—'))}")
    mode_label = {"quick": "快速巡逻", "point": "定点详查", "sweep": "环视检查"}.get(ctx.get("patrolMode"), "快速巡逻")
    lines.append(f"当前巡查方式：{mode_label}")
    weather_names = {"clear": "晴", "rain": "小雨", "storm": "大雨"}
    weather = ctx.get("weather") or "clear"
    lines.append(f"作业环境：{weather_names.get(weather, weather)}")
    if weather == "storm":
        lines.append("雨天约束（大雨）：无人机无法起飞，禁止 recheck 动作；植被缺水类异常暂缓派单，"
                     "优先处置通道占用、积水内涝；判读置信度整体下调，建议人工或固定摄像头确认")
    elif weather == "rain":
        lines.append("雨天约束（小雨）：地面反光与低照度会影响判读，植被缺水类异常暂缓派单，"
                     "其余异常建议提高复核比例后再处置")
    anomalies = ctx.get("anomalies") or []
    if anomalies:
        parts = []
        for a in anomalies[:10]:
            h = {"pending": "未处理", "processing": "处理中", "resolved": "已处置"}.get(a.get("handleStatus"), "未处理")
            parts.append(f"{a.get('label')}@{a.get('near')}（{h}）")
        lines.append(f"当前异常 {len(anomalies)} 处：{'；'.join(parts)}")
    else:
        lines.append("当前异常：无")
    return "\n".join(lines)


def _parse_agent_output(text: str, ctx: dict) -> dict:
    """容错解析模型输出 → {reply, actions}；失败时给安全兜底"""
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            reply = str(obj.get("reply") or "").strip()
            actions = obj.get("actions")
            if isinstance(actions, list):
                # 只放行已知动作类型（安全白名单）
                known = {"patrol", "switch_mode", "switch_scene", "export_report", "mark_resolved", "recheck"}
                actions = [a for a in actions if isinstance(a, dict) and a.get("type") in known]
                if reply:
                    return {"reply": reply, "actions": actions}
        except json.JSONDecodeError:
            pass
    return {"reply": "抱歉，我没太理解。可以试试：「全面体检一下」「现在有什么异常」「导出报告」。",
            "actions": []}


def _rag_block(query: str) -> tuple[str, list[str]]:
    """知识库检索 → 注入 prompt 的文本块 + 来源标题列表（无相关结果返回空）"""
    hits = kb.search(query, top_k=2)
    if not hits:
        return "（无相关内容）", []
    parts = [f"[{h['title']}] {h['text']}" for h in hits]
    return "\n".join(parts), [h["title"] for h in hits]


def _last_user_text(messages: list[dict]) -> str:
    """取最后一条用户消息文本（RAG 检索用）"""
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content")
            return c if isinstance(c, str) else ""
    return ""


def _storm_recheck_guard(text: str, ctx: dict):
    """大雨约束短路：用户要求无人机复核时，直接给出降级说明（不调模型、不下发动作）"""
    if (ctx.get("weather") or "clear") != "storm":
        return None
    if not any(k in (text or "") for k in ("复核", "复查")):
        return None
    return ("雨这么大无人机没法起飞，复核先停：建议改人工到现场确认，或者等雨停了我再飞一轮。"
            "已经确认的异常可以先标记处置，没把握的先挂起。")


@app.post("/api/agent/chat")
async def agent_chat(data: dict):
    if not (CFG.get("api_key") and CFG.get("base_url")):
        raise HTTPException(503, "模型未配置：助手将以离线规则模式工作（或填写 config.local.json 启用大模型）")

    messages = data.get("messages") or []
    if not isinstance(messages, list) or not messages:
        raise HTTPException(400, "messages 不能为空")
    # 只保留最近 8 条，防止上下文过长
    messages = [m for m in messages if isinstance(m, dict) and m.get("role") in ("user", "assistant")][-8:]

    ctx = data.get("context") or {}
    kb_block, kb_sources = _rag_block(_last_user_text(messages))
    guard = _storm_recheck_guard(_last_user_text(messages), ctx)
    if guard:
        return {"reply": guard, "actions": [], "sources": kb_sources}
    payload = {
        "model": CFG.get("model", "agnes-3.0-flash"),
        "messages": [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT.format(
                context_block=_build_context_block(ctx), knowledge_block=kb_block)},
            *messages,
        ],
        "temperature": 0.2,
        "max_tokens": 2000,
    }
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(
                f"{CFG['base_url'].rstrip('/')}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {CFG['api_key']}"},
            )
            r.raise_for_status()
            body = r.json()
    except httpx.TimeoutException:
        raise HTTPException(504, "模型调用超时")
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"模型服务返回错误 {e.response.status_code}")
    except httpx.HTTPError as e:
        raise HTTPException(502, f"模型服务连接失败：{e}")

    content = ""
    try:
        msg = body["choices"][0]["message"]
        content = msg.get("content") or ""
        if isinstance(content, list):
            content = "".join(seg.get("text", "") for seg in content if isinstance(seg, dict))
        # 推理型模型：content 为空时从 reasoning_content 兑底提取
        if not content.strip():
            rc = msg.get("reasoning_content") or ""
            if isinstance(rc, str) and rc.strip():
                content = rc
    except (KeyError, IndexError, TypeError):
        raise HTTPException(502, "模型响应格式异常")

    result = _parse_agent_output(content, ctx)
    result["sources"] = kb_sources
    return result


# ---------- 流式助手端点（SSE，前端逐字渲染） ----------
STREAM_SYSTEM_PROMPT = """你是"智巡"智能巡检平台的语音助手"小巡"。用户（园区管理员，非技术人员）用自然语言指挥平台，你负责理解意图并产出动作。

当前平台状态：
{context_block}

可执行动作（按需 0 个或多个，JSON 对象）：
- {{"type":"patrol","args":{{"zoneIds":["zone-c"],"mode":"point"}}}}  发起巡逻。zoneIds 省略=全部分区；mode：quick 快速巡逻/point 定点详查/sweep 环视检查，省略=保持当前方式
- {{"type":"switch_mode","args":{{"mode":"real"}}}}  切换数据源。sim 仿真/replay 历史回放/real 真机
- {{"type":"switch_scene","args":{{"sceneId":"warehouse"}}}}  切换巡检场景
- {{"type":"export_report","args":{{}}}}  导出 PDF 巡检报告
- {{"type":"mark_resolved","args":{{"all":true}}}}  标记异常处置完成
- {{"type":"recheck","args":{{"all":true}}}}  无人机复核全部待复核异常

输出格式（严格遵守）：
第一行起：给用户的简短中文回复，1-2 句，口语化纯文本（不要 JSON、不要 markdown、不要换行符转义）。
回复结束后，必须另起一行输出动作数组，格式：ACTIONS: [动作对象数组]，无动作时也要输出 ACTIONS: []。
示例 1（派发任务）：
好的，这就对西南分区发起定点详查。
ACTIONS: [{{"type":"patrol","args":{{"zoneIds":["zone-c"],"mode":"point"}}}}]
示例 2（仅查询）：
本轮发现 3 处异常，其中待处理 2 处。
ACTIONS: []
注意：只要回复里说了“这就/帮您”执行某操作，就必须在 ACTIONS 行给出对应动作对象，不能只在口播中表述。

规则：
1. 任务进行中（phase 不为 idle/report）时不发起 patrol，回复请用户稍候
2. 查询类问题直接依据状态信息回答，ACTIONS: []
3. 处置方法、规范、平台用法类问题，优先依据知识库参考资料回答，保持简短；与参考资料无关的平台状态问题仍依据状态信息
4. 不确定意图时友好追问，不做猜测动作
5. 雨天约束：作业环境为大雨时不要输出 recheck 动作（无人机无法起飞），改为建议人工确认；植被缺水类异常建议雨停后再处置；被问"雨天怎么巡检/器械还要不要"时，依据知识库与约束如实说明降级项

知识库参考资料（来自本地巡检知识库检索，与问题相关时可引用）：
{knowledge_block}"""


def _sse(obj: dict) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


def _local_fallback_actions(text: str, ctx: dict) -> list[dict]:
    """模型未输出 ACTIONS 协议时的本地意图解析兑底（双引擎：模型决策优先，规则引擎保底）。
    与前端离线规则引擎同语义：查询类不触发动作，指令类按关键词+分区表解析。"""
    t = text or ""
    actions: list[dict] = []
    # 查询类：不产生动作
    if any(k in t for k in ("异常", "问题", "情况", "多少")) and not any(k in t for k in ("巡", "查一查", "检查", "体检", "处置", "导出")):
        return actions
    zones = [z for z in (ctx.get("zones") or []) if isinstance(z, dict)]
    # 巡逻
    if any(k in t for k in ("巡逻", "巡检", "巡查", "检查", "体检", "详查", "查一查", "看一遍", "看下")):
        mode = "point" if ("详查" in t or "定点" in t) else ("sweep" if "环视" in t else "quick")
        zone_hit = next((z for z in zones if z.get("name") and z["name"].replace("分区", "") and z["name"].replace("分区", "") in t), None)
        if zone_hit:
            actions.append({"type": "patrol", "args": {"zoneIds": [zone_hit["id"]], "mode": mode}})
        else:
            actions.append({"type": "patrol", "args": {"mode": mode}})
    # 报告 / 处置 / 复核 / 场景 / 数据源
    if any(k in t for k in ("报告", "导出", "PDF", "pdf")):
        actions.append({"type": "export_report", "args": {}})
    if any(k in t for k in ("处理完", "已处理", "标记", "解决")):
        actions.append({"type": "mark_resolved", "args": {"all": True}})
    if any(k in t for k in ("复核", "复查")):
        # 雨天约束：大雨时无人机无法起飞，规则引擎同样不下发复核动作（与提示词约束一致）
        if (ctx.get("weather") or "clear") != "storm":
            actions.append({"type": "recheck", "args": {"all": True}})
    for kw, target in (("仓库", "warehouse"), ("园区", "park")):
        if kw in t and ctx.get("sceneId") != target:
            actions.append({"type": "switch_scene", "args": {"sceneId": target}})
            break
    for kw, m in (("真机", "real"), ("回放", "replay"), ("仿真", "sim")):
        if kw in t and ctx.get("mode") != m:
            actions.append({"type": "switch_mode", "args": {"mode": m}})
            break
    return actions


def _parse_stream_output(full: str, actions_raw: str | None) -> tuple[str, list[dict]]:
    """流式全文解析：优先 ACTIONS: 行协议，兼容旧 JSON 协议，失败给兜底"""
    known = {"patrol", "switch_mode", "switch_scene", "export_report", "mark_resolved", "recheck"}
    if actions_raw is not None:
        reply = full.split("ACTIONS:", 1)[0].strip()
        try:
            arr = json.loads(actions_raw.strip())
            if isinstance(arr, list):
                actions = [a for a in arr if isinstance(a, dict) and a.get("type") in known]
                if reply:
                    return reply, actions
        except json.JSONDecodeError:
            pass
        return (reply or "抱歉，我没太理解。可以试试：「全面体检一下」。"), []
    # 兼容：模型仍输出旧 JSON 协议
    old = _parse_agent_output(full, {})
    return old["reply"], old["actions"]


@app.post("/api/agent/chat/stream")
async def agent_chat_stream(data: dict):
    """SSE 流式助手：stage 帧（思考链）→ delta 帧（逐字回复）→ 结果帧（actions/sources/done）→ [DONE]"""

    async def gen():
        if not (CFG.get("api_key") and CFG.get("base_url")):
            yield _sse({"error": "模型未配置，即将切换离线规则模式"})
            yield "data: [DONE]\n\n"
            return
        messages = data.get("messages") or []
        if not isinstance(messages, list) or not messages:
            yield _sse({"error": "messages 不能为空"})
            yield "data: [DONE]\n\n"
            return
        messages = [m for m in messages if isinstance(m, dict) and m.get("role") in ("user", "assistant")][-8:]
        ctx = data.get("context") or {}
        # 思考链阶段 1：知识库检索（真实执行 BM25 检索）
        yield _sse({"stage": "retrieve", "text": "检索巡检知识库…"})
        kb_block, kb_sources = _rag_block(_last_user_text(messages))
        # 阶段 2：模型推理（据检索结果如实描述）
        yield _sse({"stage": "reason",
                    "text": (f"命中 {len(kb_sources)} 篇参考（{('、'.join(kb_sources[:2]))}…）" if kb_sources else "未命中知识库，按平台状态推理") + "，组织回复…"})
        # 阶段 3：动作决策（模型协议优先，本地意图解析兜底；先决策再作答，符合“检索→推理→执行→回复”链路）
        user_text = _last_user_text(messages)
        planned = _local_fallback_actions(user_text, ctx)
        action_names = {"patrol": "发起巡检", "switch_mode": "切换数据源", "switch_scene": "切换场景",
                        "export_report": "导出报告", "mark_resolved": "标记处置", "recheck": "无人机复核",
                        "workorder": "工单流转"}
        guard = _storm_recheck_guard(user_text, ctx)
        if guard:
            # 大雨复核短路：先给计划阶段帧（标注约束），再流式口播降级说明，动作数组为空
            yield _sse({"stage": "act", "text": "雨天约束：无人机复核已暂停，转人工确认"})
            yield _sse({"delta": guard})
            yield _sse({"actions": [], "sources": kb_sources, "done": True, "reply": guard})
            yield "data: [DONE]\n\n"
            return
        if planned:
            yield _sse({"stage": "act",
                        "text": "解析指令 → 计划执行：" + "、".join(action_names.get(a["type"], a["type"]) for a in planned)})
        payload = {
            "model": CFG.get("model", "agnes-3.0-flash"),
            "messages": [
                {"role": "system", "content": STREAM_SYSTEM_PROMPT.format(
                    context_block=_build_context_block(ctx), knowledge_block=kb_block)},
                *messages,
            ],
            "temperature": 0.2,
            "max_tokens": 2000,
            "stream": True,
        }
        try:
            client = httpx.AsyncClient(timeout=90)
            req = client.build_request(
                "POST", f"{CFG['base_url'].rstrip('/')}/chat/completions",
                json=payload, headers={"Authorization": f"Bearer {CFG['api_key']}"},
            )
            r = await client.send(req, stream=True)
            if r.status_code != 200:
                await r.aclose()
                await client.aclose()
                yield _sse({"error": f"模型服务返回错误 {r.status_code}"})
                yield "data: [DONE]\n\n"
                return
        except httpx.HTTPError as e:
            yield _sse({"error": f"模型服务连接失败：{e}"})
            yield "data: [DONE]\n\n"
            return

        full = ""
        sent = 0            # 已转发到 full 的字符数
        actions_raw = None  # ACTIONS: 之后的内容（None = 尚未出现）
        try:
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    obj = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                try:
                    delta = obj["choices"][0]["delta"].get("content") or ""
                except (KeyError, IndexError, AttributeError):
                    delta = ""
                if not delta:
                    continue
                full += delta
                if actions_raw is None:
                    idx = full.find("ACTIONS:")
                    if idx >= 0:
                        # ACTIONS 出现：补发其之前的正文，之后停止转发
                        if idx > sent:
                            yield _sse({"delta": full[sent:idx]})
                        sent = idx
                        actions_raw = full[idx + len("ACTIONS:"):]
                    else:
                        # 保留尾部若干字符，防止 ACTIONS: 标记被 chunk 截断后误转发
                        safe = max(len(full) - 12, sent)
                        if safe > sent:
                            yield _sse({"delta": full[sent:safe]})
                            sent = safe
        except httpx.HTTPError:
            pass  # 流中断：以已收到的内容收尾
        finally:
            await r.aclose()
            await client.aclose()

        if actions_raw is None:
            idx = full.find("ACTIONS:")
            if idx >= 0:
                if idx > sent:
                    yield _sse({"delta": full[sent:idx]})
                actions_raw = full[idx + len("ACTIONS:"):]
            elif len(full) > sent:
                yield _sse({"delta": full[sent:]})

        reply, actions = _parse_stream_output(full, actions_raw)
        # 双引擎兜底：模型口播有执行意图但未输出动作协议时，本地规则解析补发
        used_fallback = False
        if not actions:
            if planned:
                actions = planned
                used_fallback = True
        # 阶段 3b：模型自主输出协议且与本地预判不一致时，补播真实动作
        if actions and not used_fallback and actions != planned:
            yield _sse({"stage": "act", "text": f"执行 {len(actions)} 个动作：" + "、".join(action_names.get(a["type"], a["type"]) for a in actions)})
        # 兼容模式：模型输出了旧 JSON 协议，正文已被流成 JSON 字符——发 reset 帧让前端替换为纯回复
        if actions_raw is None and full.lstrip().startswith("{"):
            yield _sse({"reset": True, "reply": reply})
        elif reply and (len(reply) > sent or not full):
            pass  # 正文已随流转发
        yield _sse({"actions": actions, "sources": kb_sources, "done": True, "reply": reply})
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============================================================
# MCP 桥接层 —— 让标准 MCP 客户端（Claude/Cursor/TeleAgent 等）
# 能够查询平台状态并指挥巡检作业
# ------------------------------------------------------------
# 数据流：前端定期上报快照 → STATE；MCP Server（server/mcp_server.py，
# FastMCP streamable-http :8790）经 REST 读取 STATE、POST 指令到
# 总线；前端经 SSE /api/mcp/events 订阅指令并执行（复用 Agent 动作链）。
# ============================================================
import time as _time

STATE: dict = {"updated": 0, "online": False, "data": None}
_CMD_SUBSCRIBERS: list["asyncio.Queue"] = []


@app.post("/api/state")
async def push_state(data: dict):
    """前端上报平台状态快照（供 MCP 查询）"""
    STATE["data"] = data
    STATE["updated"] = _time.time()
    STATE["online"] = True
    return {"ok": True}


@app.get("/api/state")
async def read_state():
    """读取最新快照（MCP Server / 调试用）；超过 15s 未上报视为前端离线"""
    fresh = (_time.time() - STATE["updated"]) < 15
    STATE["online"] = STATE["online"] and fresh
    return {
        "online": STATE["online"],
        "stale": not fresh,
        "updated": STATE["updated"],
        "data": STATE["data"],
    }


@app.post("/api/mcp/cmd")
async def push_mcp_cmd(data: dict):
    """MCP 指令入总线（type/args），由订阅 /api/mcp/events 的前端执行"""
    cmd = {
        "type": data.get("type"),
        "args": data.get("args") or {},
        "source": data.get("source") or "mcp",
        "ts": _time.time(),
    }
    if not cmd["type"]:
        raise HTTPException(400, "type 不能为空")
    for q in _CMD_SUBSCRIBERS:
        q.put_nowait(cmd)
    return {"ok": True, "delivered": len(_CMD_SUBSCRIBERS), "cmd": cmd}


@app.get("/api/mcp/events")
async def mcp_events():
    """SSE 指令通道：前端订阅后实时接收 MCP 下发的动作指令"""
    import asyncio

    q: asyncio.Queue = asyncio.Queue()
    _CMD_SUBSCRIBERS.append(q)

    async def gen():
        try:
            yield "data: " + json.dumps({"type": "hello", "args": {}}, ensure_ascii=False) + "\n\n"
            while True:
                try:
                    cmd = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield "data: " + json.dumps(cmd, ensure_ascii=False) + "\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            _CMD_SUBSCRIBERS.remove(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Access-Control-Allow-Origin": "*"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(CFG.get("port", 8788)))
