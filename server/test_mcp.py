# ============================================================
# MCP Server 端到端测试（test_mcp.py）
# ------------------------------------------------------------
# 前置：后端 8788 与 MCP Server 8790 已启动（CI 中由工作流拉起）
# 断言：
#   1. tools/list 暴露 6 个 smartpatrol_* 工具
#   2. get_park_status：前端不在线时返回结构化错误提示（不崩溃）
#   3. start_patrol 分区解析：非法分区返回 hint 列表
#   4. execute_action：未知动作返回 valid_types 引导
# 运行：uv run python test_mcp.py
# ============================================================
import asyncio
import json
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

MCP_URL = "http://127.0.0.1:8790/mcp"
EXPECTED_TOOLS = {
    "smartpatrol_get_park_status",
    "smartpatrol_list_anomalies",
    "smartpatrol_start_patrol",
    "smartpatrol_execute_action",
    "smartpatrol_ask_assistant",
    "smartpatrol_recognize_image",
}


def _content_text(res) -> str:
    return "".join(c.text for c in res.content if getattr(c, "text", None))


def _as_json(text: str) -> dict:
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.startswith("json"):
            s = s[4:]
    return json.loads(s)


async def main():
    async with streamablehttp_client(MCP_URL) as (r, w, _):
        async with ClientSession(r, w) as session:
            await session.initialize()

            # 1) 工具清单
            tools = (await session.list_tools()).tools
            names = {t.name for t in tools}
            missing = EXPECTED_TOOLS - names
            assert not missing, f"缺少工具: {missing}"
            print(f"PASS 工具清单：{len(names)} 个（{', '.join(sorted(names))}）")

            # 2) 状态查询：前端不在线时返回结构化提示（在线时返回真实数据，同样通过）
            res = await session.call_tool("smartpatrol_get_park_status", {})
            data = _as_json(_content_text(res))
            assert "error" in data or "phase" in data, f"返回异常: {data}"
            tag = "前端在线(真实数据)" if "phase" in data else "前端离线(结构化提示)"
            assert res.isError is not True or "error" in data
            print(f"PASS 状态查询：{tag} —— {json.dumps(data, ensure_ascii=False)[:80]}...")

            # 3) 分区解析容错：非法分区名 → 报错并给出可用分区
            res = await session.call_tool("smartpatrol_start_patrol", {"zone_names": "不存在的分区", "mode": "quick"})
            data = _as_json(_content_text(res))
            if "error" in data:
                assert "hint" in data or "可用分区" in json.dumps(data, ensure_ascii=False), f"缺少引导: {data}"
                print("PASS 分区容错：非法分区返回可用分区提示")
            else:
                assert data.get("ok") is True, f"意外返回: {data}"
                print("PASS 分区解析：指令已下发（前端在线）")

            # 4) 非法动作类型 → 返回 valid_types 引导
            res = await session.call_tool("smartpatrol_execute_action", {"action_type": "自爆", "args_json": "{}"})
            data = _as_json(_content_text(res))
            assert "valid_types" in data, f"缺少 valid_types: {data}"
            print(f"PASS 动作校验：非法动作返回白名单 {data['valid_types']}")

    print("==== MCP Server 端到端测试全部通过 ====")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as e:
        print(f"FAIL: {e}")
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR（连接失败？后端/MCP服务未启动）: {e}")
        sys.exit(1)
