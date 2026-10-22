# -*- coding: utf-8 -*-
"""AI 巡检助手单测：mock 模型服务验证 /api/agent/chat（意图解析/上下文注入/容错/白名单）"""
import threading
import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import main as main_mod
from main import app, _build_context_block, _parse_agent_output

# ---------- 1. 上下文构造单测 ----------
ctx = {
    "sceneId": "park", "sceneName": "园区场景",
    "scenes": [{"id": "park", "name": "园区场景"}, {"id": "warehouse", "name": "室内仓库"}],
    "zones": [{"id": "zone-c", "name": "西南分区"}],
    "mode": "sim", "phase": "idle", "patrolMode": "quick",
    "anomalies": [{"label": "垃圾分类违规", "near": "3号垃圾桶", "handleStatus": "pending"}],
}
block = _build_context_block(ctx)
for kw in ["园区场景", "室内仓库", "西南分区", "仿真模式", "待命", "快速巡逻", "未处理"]:
    assert kw in block, f"上下文缺少 {kw}"
assert "当前异常 1 处" in block
# 空异常
block2 = _build_context_block({"sceneName": "x", "zones": [], "mode": "real", "phase": "patrol"})
assert "当前异常：无" in block2 and "真机模式" in block2 and "巡逻中" in block2
print(f"上下文构造: 通过（{len(block)} 字符）")

# ---------- 2. 输出解析单测 ----------
cases = [
    ('{"reply":"好的","actions":[{"type":"patrol","args":{"zoneIds":["zone-c"],"mode":"point"}}]}',
     dict(reply="好的", n_actions=1, a0="patrol")),
    ('```json\n{"reply":"收到","actions":[{"type":"switch_mode","args":{"mode":"real"}},{"type":"delete_database","args":{}}]}\n```',
     dict(reply="收到", n_actions=1, a0="switch_mode")),   # 未知动作被白名单过滤
    ('{"reply":"无动作","actions":[]}', dict(reply="无动作", n_actions=0)),
    ('模型抽风没有 JSON', dict(reply="没太理解", n_actions=0)),   # 兜底回复
]
for text, exp in cases:
    r = _parse_agent_output(text, {})
    assert exp["reply"] in r["reply"], f"{text[:30]}… reply 应含 {exp['reply']}"
    assert len(r["actions"]) == exp["n_actions"], f"{text[:30]}… 动作数 {len(r['actions'])} != {exp['n_actions']}"
    if exp.get("a0"):
        assert r["actions"][0]["type"] == exp["a0"]
print(f"输出解析: {len(cases)}/{len(cases)} 通过")

# ---------- 3. mock 模型服务（校验 system prompt 注入了上下文） ----------
MOCK_PORT = 18998
MOCK_URL = f"http://127.0.0.1:{MOCK_PORT}/v1"
seen_prompts = []

mock = FastAPI()

@mock.post("/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    seen_prompts.append(body["messages"][0]["content"])
    user_msg = [m for m in body["messages"] if m["role"] == "user"][-1]["content"]
    if "西南" in user_msg:
        return {"choices": [{"message": {"content":
            '{"reply":"好的，马上安排西南分区定点详查。","actions":[{"type":"patrol","args":{"zoneIds":["zone-c"],"mode":"point"}}]}'}}]}
    return {"choices": [{"message": {"content":
        '{"reply":"当前共 1 处异常未处理：垃圾分类违规（3号垃圾桶）。","actions":[]}'}}]}

server = uvicorn.Server(uvicorn.Config(mock, host="127.0.0.1", port=MOCK_PORT, log_level="warning"))
t = threading.Thread(target=server.run, daemon=True)
t.start()
time.sleep(1.2)

main_mod.CFG = {"base_url": MOCK_URL, "api_key": "test-key", "model": "test-model"}
client = TestClient(app)

# ---------- 4. 全链路 ----------
r = client.post("/api/agent/chat", json={
    "messages": [{"role": "user", "content": "帮我检查一下西南区"}],
    "context": ctx,
})
assert r.status_code == 200, r.text
d = r.json()
assert d["reply"].startswith("好的") and d["actions"][0]["type"] == "patrol"
assert d["actions"][0]["args"]["zoneIds"] == ["zone-c"]
# system prompt 应含运行状态上下文
assert "西南分区" in seen_prompts[-1] and "仿真模式" in seen_prompts[-1] and "未处理" in seen_prompts[-1]
print(f"意图解析→巡逻: 通过（{d['reply']}）")

r2 = client.post("/api/agent/chat", json={
    "messages": [{"role": "user", "content": "现在有什么异常？"}],
    "context": ctx,
})
d2 = r2.json()
assert "垃圾分类违规" in d2["reply"] and d2["actions"] == []
print(f"查询类直答: 通过（{d2['reply']}）")

# 空 messages 400
r3 = client.post("/api/agent/chat", json={"messages": [], "context": {}})
assert r3.status_code == 400
print("空消息 400: 通过")

# 未配置模型 503
main_mod.CFG = {}
r4 = client.post("/api/agent/chat", json={"messages": [{"role": "user", "content": "hi"}], "context": {}})
assert r4.status_code == 503
print("未配置模型 503: 通过")

print("\n==== 助手接口单测全部通过 ====")
