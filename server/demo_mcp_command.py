# -*- coding: utf-8 -*-
"""MCP 跨智能体指挥演示脚本：模拟外部 AI 客户端指挥平台完整流程
用法：连接 MCP Server（8790），按剧本依次调用工具，展示"外部智能体指挥巡检平台"全链路。
场景：物业值班员不在平台页面，由另一个 AI 助手代为指挥——查状态 → 派任务 → 看结果 → 出报告。
"""
import asyncio
import json
import sys
import time

sys.path.insert(0, r"D:\smartpatrol-web\smartpatrol-app\server")

MCP_URL = "http://127.0.0.1:8790/mcp"

# ---------- 极简 MCP streamable-http 客户端（不依赖 mcp 包，便于独立运行） ----------
import httpx

class McpDemo:
    def __init__(self, url):
        self.url = url
        self.session_id = None
        self._id = 0
        self.tools = []

    async def _post(self, method, params=None):
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        body = {"jsonrpc": "2.0", "id": self._id + 1, "method": method}
        self._id += 1
        if params is not None:
            body["params"] = params
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(self.url, json=body, headers=headers)
            sid = r.headers.get("mcp-session-id")
            if sid:
                self.session_id = sid
            r.raise_for_status()
            text = r.text
        # 兼容 SSE 与 JSON 两种返回
        for line in text.splitlines():
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"error": "unparseable", "raw": text[:200]}

    async def init(self):
        r = await self._post("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "smartpatrol-demo", "version": "1.0"},
        })
        await self._post("notifications/initialized")
        return r

    async def list_tools(self):
        r = await self._post("tools/list")
        self.tools = r.get("result", {}).get("tools", [])
        return self.tools

    async def call(self, name, args=None):
        r = await self._post("tools/call", {"name": name, "arguments": args or {}})
        content = r.get("result", {}).get("content", [])
        return content[0].get("text", "") if content else json.dumps(r, ensure_ascii=False)[:300]


async def main():
    print("=" * 62)
    print("MCP 跨智能体指挥演示 —— 外部 AI 客户端指挥智巡平台")
    print("=" * 62)

    mcp = McpDemo(MCP_URL)

    # 1. 初始化
    info = await mcp.init()
    print("\n[1] 握手:", info.get("result", {}).get("serverInfo", {}))

    # 2. 工具清单
    tools = await mcp.list_tools()
    print(f"\n[2] 发现已注册 {len(tools)} 个工具：")
    for t in tools:
        print(f"    - {t['name']}")

    # 3. 查园区状态（剧情：外部助手先了解现场）
    print("\n[3] 调用 smartpatrol_get_park_status：")
    status = await mcp.call("smartpatrol_get_park_status")
    print("   ", status[:200])

    # 4. 派双车任务（剧情：让平台出车）
    print("\n[4] 调用 smartpatrol_start_patrol（两台车分头查全园）：")
    r = await mcp.call("smartpatrol_start_patrol", {"mode": "quick", "fleet": 2, "desc": "全园"})
    print("   ", r[:200])

    # 5. 轮询等待任务完成（通过状态接口看阶段）
    print("\n[5] 等待任务完成（轮询状态 35s）…")
    deadline = time.time() + 35
    done = False
    while time.time() < deadline:
        s = await mcp.call("smartpatrol_get_park_status")
        if "已完成" in s or "report" in s:
            done = True
            print("   状态:", s[:150])
            break
        await asyncio.sleep(5)
    if not done:
        print("    （演示脚本不阻塞等待，继续）")

    # 6. 查异常清单
    print("\n[6] 调用 smartpatrol_list_anomalies：")
    anomalies = await mcp.call("smartpatrol_list_anomalies")
    print("   ", anomalies[:220])

    # 7. 知识问答（复用 RAG）
    print("\n[7] 调用 smartpatrol_ask_assistant（雨天要不要看烟头）：")
    ans = await mcp.call("smartpatrol_ask_assistant", {"message": "下大雨还要看烟头吗"})
    print("   ", ans[:220])

    print("\n" + "=" * 62)
    print("演示完成：外部智能体通过 6 个标准 MCP 工具完成了")
    print("查状态 → 派双车 → 等结果 → 看异常 → 问知识 的完整指挥链")
    print("=" * 62)


if __name__ == "__main__":
    asyncio.run(main())