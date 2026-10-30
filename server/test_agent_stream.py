# -*- coding: utf-8 -*-
"""流式助手单测：SSE 帧序列 / ACTIONS 行解析 / chunk 截断 / 旧 JSON 兼容 / 未配置降级"""
import json
import threading
import time

from fastapi.testclient import TestClient
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import uvicorn

import main as main_mod

MOCK_PORT = 18992
MOCK_URL = f"http://127.0.0.1:{MOCK_PORT}/v1"
CAPTURED = {}

mock = FastAPI()


def _sse_chunk(content: str) -> str:
    return "data: " + json.dumps({"choices": [{"delta": {"content": content}}]}, ensure_ascii=False) + "\n\n"


@mock.post("/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    assert body.get("stream") is True, "流式端点必须以 stream=True 调用模型"
    CAPTURED["system"] = body["messages"][0]["content"]
    chunks = CAPTURED["chunks"]
    async def gen():
        for c in chunks:
            yield _sse_chunk(c)
        yield "data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")


server = uvicorn.Server(uvicorn.Config(mock, host="127.0.0.1", port=MOCK_PORT, log_level="warning"))
t = threading.Thread(target=server.run, daemon=True)
t.start()
time.sleep(1.2)

main_mod.CFG = {"base_url": MOCK_URL, "api_key": "test-key", "model": "test-model"}
client = TestClient(main_mod.app)


def post_stream(user_text: str) -> list[dict]:
    r = client.post("/api/agent/chat/stream", json={
        "messages": [{"role": "user", "content": user_text}],
        "context": {"sceneName": "智慧园区", "sceneId": "park", "phase": "idle"},
    })
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    frames = []
    for block in r.text.split("\n\n"):
        block = block.strip()
        if block.startswith("data: "):
            payload = block[6:]
            frames.append("[DONE]" if payload == "[DONE]" else json.loads(payload))
    return frames


def collect(frames):
    """从帧序列提取 (拼接正文, 结果帧)"""
    text = "".join(f["delta"] for f in frames if isinstance(f, dict) and "delta" in f)
    final = next((f for f in frames if isinstance(f, dict) and f.get("done")), None)
    return text, final


CTX = {"sceneName": "智慧园区", "sceneId": "park", "phase": "idle", "mode": "sim"}

# 用例 1：标准 ACTIONS: 行（单块完整出现）
CAPTURED["chunks"] = [
    "好的，马上安排西南分区定点详查。\n",
    "ACTIONS: [{\"type\": \"patrol\", \"args\": {\"zoneIds\": [\"zone-c\"], \"mode\": \"point\"}}]",
]
frames = post_stream("帮我详查西南分区")
text, final = collect(frames)
assert text == "好的，马上安排西南分区定点详查。\n".rstrip() or "西南分区" in text, f"正文拼接异常: {text!r}"
assert "ACTIONS" not in text, f"ACTIONS 行泄漏到正文: {text!r}"
assert final and final["done"] is True, f"缺收尾帧: {frames}"
assert any(a["type"] == "patrol" for a in final["actions"]), f"动作解析失败: {final}"
assert frames[-1] == "[DONE]", "缺 [DONE] 结尾"
print(f"用例1 标准 ACTIONS 行: 通过（正文={text!r}，actions={final['actions']}）")

# 用例 2：ACTIONS: 标记跨 chunk 截断
CAPTURED["chunks"] = [
    "好的，马上出发。",
    "ACT",
    "IONS: []",
]
frames = post_stream("全面体检一下")
text, final = collect(frames)
assert "ACT" not in text and "ACTIONS" not in text, f"截断标记泄漏: {text!r}"
assert final and final["actions"] == [], f"空动作应解析为 []: {final}"
print(f"用例2 ACTIONS 跨块截断: 通过（正文={text!r}）")

# 用例 3：旧 JSON 协议兼容（模型仍输出 {"reply":...}）
CAPTURED["chunks"] = [
    '{"reply": "好的，已',
    '发起全园体检。", "actions": [{"type": "patrol", "args": {}}]}',
]
frames = post_stream("全面体检一下")
text, final = collect(frames)
# reset 帧应出现，正文被替换为纯回复
reset = next((f for f in frames if isinstance(f, dict) and f.get("reset")), None)
assert reset is not None, f"旧 JSON 应触发 reset 帧: {frames}"
assert "全园体检" in reset["reply"], f"reset 回复异常: {reset}"
assert final and any(a["type"] == "patrol" for a in final["actions"]), f"旧 JSON 动作解析失败: {final}"
print(f"用例3 旧 JSON 兼容: 通过（reset={reset['reply']!r}）")

# 用例 4：RAG 注入（知识类问题）
CAPTURED["chunks"] = [
    "垃圾分类违规请通知保洁 15 分钟内到场清理。",
    "ACTIONS: []",
]
frames = post_stream("垃圾分类违规怎么处置")
sys_prompt = CAPTURED.get("system", "")
assert "知识库参考资料" in sys_prompt and "拍照取证" in sys_prompt, f"流式端点未注入知识片段: {sys_prompt[:200]}"
_, final = collect(frames)
assert final["sources"], f"流式 sources 缺失: {final}"
print(f"用例4 流式 RAG 注入: 通过（sources={final['sources']}）")

# 用例 5：未配置模型 → error 帧 + [DONE]，不崩溃
main_mod.CFG = {}
frames = post_stream("你好")
assert any(isinstance(f, dict) and f.get("error") for f in frames), f"缺 error 帧: {frames}"
assert frames[-1] == "[DONE]"
print("用例5 未配置模型 error 帧: 通过")

# 恢复配置（供后续测试文件使用）
main_mod.CFG = {"base_url": MOCK_URL, "api_key": "test-key", "model": "test-model"}
print("==== 流式助手单测全部通过 ====")
