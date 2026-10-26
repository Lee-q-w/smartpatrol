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

# 本地开发跨域（vite dev 端口）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5199", "http://127.0.0.1:5199"],
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
注意：摆放在路侧/路边的交通锥、施工围挡属于园区正常设施，不构成异常；仅当安全出口、疏散通道或消防通道被实际堵塞时才判 blocked。
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
4. 不确定意图时友好追问，不做猜测动作"""


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
    payload = {
        "model": CFG.get("model", "agnes-3.0-flash"),
        "messages": [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT.format(context_block=_build_context_block(ctx))},
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

    return _parse_agent_output(content, ctx)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(CFG.get("port", 8788)))
