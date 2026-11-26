# ============================================================
# 智巡 SmartPatrol · MCP Server
# ------------------------------------------------------------
# 把巡检平台能力暴露为标准 MCP（Model Context Protocol）工具，
# 供 Claude Desktop / Cursor / TeleAgent 等任意 MCP 客户端调用：
#   - 查询园区状态与异常 (get_park_status / list_anomalies)
#   - 指挥巡逻与平台动作 (start_patrol / execute_action)
#   - AI 能力：RAG 知识问答 / 图像异常识别
#
# 架构：本服务经 HTTP 调用智巡薄后端（main.py :8788）：
#   GET  /api/state      读平台实时快照（前端定期上报）
#   POST /api/mcp/cmd    下发动作指令（前端经 /api/mcp/events 订阅执行）
#   POST /api/agent/chat RAG 增强问答
#   POST /api/recognize  图像异常识别
# 传输：Streamable HTTP（默认 http://127.0.0.1:8790/mcp）
# 依赖：mcp（FastMCP）、httpx（uv 管理）
# ============================================================
import base64
import json
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP

BACKEND = "http://127.0.0.1:8788"   # 智巡薄后端地址

mcp = FastMCP(
    "smartpatrol",
    instructions=(
        "智巡 SmartPatrol——虚实结合的园区智能巡检平台。"
        "可用工具查询园区状态、异常详情，并以指令方式指挥巡逻车作业"
        "（发起巡检、切换数据源、导出报告、处置异常等）。"
        "动作执行是异步的：指令送达后前端界面会实时执行，可用 get_park_status 观察结果。"
    ),
)


async def _backend_get(path: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{BACKEND}{path}")
        r.raise_for_status()
        return r.json()


async def _backend_post(path: str, payload: dict, timeout: float = 90) -> dict:
    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.post(f"{BACKEND}{path}", json=payload)
        r.raise_for_status()
        return r.json()


# ---------- 工具 1：园区状态总览 ----------
@mcp.tool()
async def smartpatrol_get_park_status() -> str:
    """获取园区巡检平台当前状态总览：数据源模式（仿真/回放/真机）、任务阶段、
    巡逻车电量与位置、当前场景、异常统计（待处理/处理中/已处理）。"""
    try:
        state = await _backend_get("/api/state")
    except httpx.HTTPError as e:
        return json.dumps({"error": f"后端服务不可达：{e}。请先启动智巡后端（server/main.py）与前端页面。"},
                          ensure_ascii=False)
    if not state.get("online") or not state.get("data"):
        return json.dumps({
            "error": "平台前端未连接（状态快照过期或未上报）。",
            "hint": "请打开智巡前端页面（默认 http://127.0.0.1:5199），页面在线时会自动上报状态。",
        }, ensure_ascii=False)
    d = state["data"]
    summary = {
        "scene": d.get("scene"),
        "mode": d.get("mode"),
        "phase": d.get("phase"),
        "patrol_mode": d.get("patrolMode"),
        "agv": {"battery": d.get("battery"), "position": d.get("position"), "status": d.get("agvStatus")},
        "zones": [z.get("name", z.get("id")) for z in d.get("zones", [])],
        "anomaly_stats": d.get("stats"),
        "report_generated": d.get("reportGenerated"),
        "updated": state.get("updated"),
    }
    return json.dumps(summary, ensure_ascii=False, indent=2)


# ---------- 工具 2：异常清单 ----------
@mcp.tool()
async def smartpatrol_list_anomalies(status: str = "") -> str:
    """列出当前巡检发现的异常清单。每条含 id、类型、位置、AI 把握度、复核状态与处置状态。

    Args:
        status: 处置状态过滤，可选 pending（未处理）/ processing（处理中）/ resolved（已处理），留空返回全部
    """
    try:
        state = await _backend_get("/api/state")
    except httpx.HTTPError as e:
        return json.dumps({"error": f"后端服务不可达：{e}"}, ensure_ascii=False)
    if not state.get("online") or not state.get("data"):
        return json.dumps({"error": "平台前端未连接，无法获取实时异常。"}, ensure_ascii=False)
    anomalies = state["data"].get("anomalies", [])
    if status:
        anomalies = [a for a in anomalies if (a.get("handleStatus") or "pending") == status]
    if not anomalies:
        return json.dumps({"message": "当前没有匹配的异常记录。", "count": 0}, ensure_ascii=False)
    out = [{"id": a.get("id"), "type": a.get("type"), "label": a.get("label"),
            "location": a.get("near"), "zone": a.get("zoneName"),
            "confidence": a.get("confidence"), "stage": a.get("stage"),
            "handle_status": a.get("handleStatus") or "pending",
            "evidence": a.get("evidence")} for a in anomalies]
    return json.dumps({"count": len(out), "anomalies": out}, ensure_ascii=False, indent=2)


# ---------- 工具 3：发起巡检 ----------
@mcp.tool()
async def smartpatrol_start_patrol(zone_names: str = "", mode: str = "quick") -> str:
    """向巡逻车下发巡检任务（前端界面会实时执行，可在平台页面观察过程）。

    Args:
        zone_names: 巡逻范围分区名，多个用顿号分隔（如"西南分区、西北分区"）；留空=全园
        mode: 巡查方式：quick 快速巡逻 / point 定点详查 / sweep 环视检查
    """
    if mode not in ("quick", "point", "sweep"):
        return json.dumps({"error": "mode 仅支持 quick / point / sweep"}, ensure_ascii=False)
    args: dict = {"mode": mode}
    if zone_names.strip():
        # 分区名 → zoneId 映射（以后端快照为准，前端执行时同样校验）
        try:
            state = await _backend_get("/api/state")
            zones = (state.get("data") or {}).get("zones", [])
            wanted = [z.strip() for z in zone_names.replace("、", ",").split(",") if z.strip()]
            ids = [z["id"] for z in zones if z.get("name") in wanted or z.get("id") in wanted]
            if not ids:
                return json.dumps({"error": f"未找到分区「{zone_names}」",
                                   "hint": f"可用分区：{[z.get('name') for z in zones]}"}, ensure_ascii=False)
            args["zoneIds"] = ids
        except httpx.HTTPError:
            return json.dumps({"error": "后端服务不可达，无法解析分区。"}, ensure_ascii=False)
    try:
        r = await _backend_post("/api/mcp/cmd", {"type": "patrol", "args": args})
    except httpx.HTTPError as e:
        return json.dumps({"error": f"指令下发失败：{e}"}, ensure_ascii=False)
    if not r.get("delivered"):
        return json.dumps({"error": "平台前端未订阅指令通道，请先打开智巡前端页面。"}, ensure_ascii=False)
    return json.dumps({"ok": True, "message": f"巡检指令已下发（范围={zone_names or '全园'}，方式={mode}），"
                                              f"前端正在执行，可用 smartpatrol_get_park_status 查看进度。",
                       "phase_expect": "patrol"}, ensure_ascii=False)


# ---------- 工具 4：通用平台动作 ----------
@mcp.tool()
async def smartpatrol_execute_action(action_type: str, args_json: str = "{}") -> str:
    """执行平台控制动作（与平台内置 AI 助手同一套动作协议，前端实时执行）。

    Args:
        action_type: 动作类型：
            switch_mode 切换数据源（args: {"mode": "sim|replay|real"}）
            switch_scene 切换巡检场景（args: {"sceneId": "park|warehouse|campus"}）
            export_report 导出 PDF 巡检报告（args: {}）
            mark_resolved 标记全部异常处置完成（args: {}）
            recheck 无人机复核全部待复核异常（args: {}）
            workorder 工单流转（args: {"anomalyId": "...", "to": "processing|resolved|pending"}）
        args_json: 动作参数（JSON 字符串，无参数用 "{}"）
    """
    try:
        args = json.loads(args_json) if args_json.strip() else {}
    except json.JSONDecodeError:
        return json.dumps({"error": "args_json 不是合法 JSON"}, ensure_ascii=False)
    valid = {"switch_mode", "switch_scene", "export_report", "mark_resolved", "recheck", "workorder"}
    if action_type not in valid:
        return json.dumps({"error": f"未知动作 {action_type}", "valid_types": sorted(valid)}, ensure_ascii=False)
    try:
        r = await _backend_post("/api/mcp/cmd", {"type": action_type, "args": args})
    except httpx.HTTPError as e:
        return json.dumps({"error": f"指令下发失败：{e}"}, ensure_ascii=False)
    if not r.get("delivered"):
        return json.dumps({"error": "平台前端未订阅指令通道，请先打开智巡前端页面。"}, ensure_ascii=False)
    return json.dumps({"ok": True, "action": action_type, "args": args,
                       "message": "指令已下发，前端正在执行。"}, ensure_ascii=False)


# ---------- 工具 5：AI 助手问答（RAG 增强） ----------
@mcp.tool()
async def smartpatrol_ask_assistant(message: str) -> str:
    """向智巡 AI 助手"小巡"提问。支持两类问题：
    1. 业务/规范类（如"垃圾分类违规怎么处置"）——检索本地巡检知识库后作答，回答附引用来源；
    2. 平台状态类（如"现在有多少异常"）——基于实时状态直答。

    Args:
        message: 用自然语言提问
    """
    try:
        r = await _backend_post("/api/agent/chat",
                                {"messages": [{"role": "user", "content": message}], "context": {}})
    except httpx.HTTPError as e:
        return json.dumps({"error": f"后端服务不可达：{e}（模型未配置时助手不可用）"}, ensure_ascii=False)
    return json.dumps({"reply": r.get("reply"),
                       "sources": r.get("sources", []),
                       "actions_executed_by_frontend": r.get("actions", [])},
                      ensure_ascii=False, indent=2)


# ---------- 工具 6：图像异常识别 ----------
@mcp.tool()
async def smartpatrol_recognize_image(image_path: str) -> str:
    """对本地图片做 AI 异常识别（多模态大模型判读园区异常：
    未熄烟头/植被缺水/垃圾分类违规/货物堆放违规/通道占用）。

    Args:
        image_path: 本地图片文件绝对路径（jpg/png）
    """
    p = Path(image_path)
    if not p.is_file():
        return json.dumps({"error": f"文件不存在：{image_path}"}, ensure_ascii=False)
    if p.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
        return json.dumps({"error": "仅支持 jpg/jpeg/png/webp/bmp 图片"}, ensure_ascii=False)
    mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    async with httpx.AsyncClient(timeout=90) as c:
        r = await c.post(f"{BACKEND}/api/recognize",
                         files={"file": (p.name, p.read_bytes(), mime)})
        r.raise_for_status()
        return json.dumps(r.json(), ensure_ascii=False, indent=2)


# ---------- 启动：Streamable HTTP，默认 http://127.0.0.1:8790/mcp ----------
if __name__ == "__main__":
    import sys
    host = "127.0.0.1"
    port = 8790
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    mcp.settings.host = host
    mcp.settings.port = port
    print(f"[smartpatrol-mcp] MCP Server 启动：http://{host}:{port}/mcp （依赖后端 {BACKEND}）")
    mcp.run(transport="streamable-http")
