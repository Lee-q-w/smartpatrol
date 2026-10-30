# -*- coding: utf-8 -*-
"""RAG 知识库单测：检索相关性 + 助手回答的知识注入"""
import json
import threading
import time

from fastapi.testclient import TestClient
from fastapi import FastAPI, Request
import uvicorn

import knowledge_base as kb
import main as main_mod

# ---------- 1. 检索器单测 ----------
stats = kb.stats()
assert stats["chunks"] >= 10 and stats["files"] >= 3, f"知识库加载异常: {stats}"
print(f"知识库加载: 通过（{stats}）")

cases = [
    ("垃圾分类违规怎么处置", "垃圾分类违规", True),
    ("未熄烟头怎么处理", "未熄烟头", True),
    ("安全出口占用怎么办", "通道占用", True),
    ("无人机复核流程是什么", "无人机复核", True),
    ("把握程度什么含义", "把握程度", True),
    ("怎么导出报告", "报告导出", True),
    ("你好", None, False),
    ("今天天气怎么样", None, False),
]
hits_ok = 0
for q, expect_title, expect_hit in cases:
    hits = kb.search(q, top_k=2)
    assert bool(hits) == expect_hit, f"{q!r} 期望命中={expect_hit}，实际 {hits}"
    if expect_hit:
        assert any(expect_title in h["title"] for h in hits), f"{q!r} 应命中 {expect_title}，实际 {[h['title'] for h in hits]}"
        assert all(h["text"] and h["source"].endswith(".md") for h in hits)
    hits_ok += 1
print(f"检索相关性: {hits_ok}/{len(cases)} 通过")

# ---------- 2. mock 模型服务（非流式 chat），校验 RAG 注入 ----------
MOCK_PORT = 18991
MOCK_URL = f"http://127.0.0.1:{MOCK_PORT}/v1"
CAPTURED = {}

mock = FastAPI()

@mock.post("/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    CAPTURED["system"] = body["messages"][0]["content"]
    return {"choices": [{"message": {"content": '{"reply": "垃圾分类违规请通知保洁 15 分钟内到场清理，30 分钟内完成处置。", "actions": []}'}}]}

server = uvicorn.Server(uvicorn.Config(mock, host="127.0.0.1", port=MOCK_PORT, log_level="warning"))
t = threading.Thread(target=server.run, daemon=True)
t.start()
time.sleep(1.2)

main_mod.CFG = {"base_url": MOCK_URL, "api_key": "test-key", "model": "test-model"}
client = TestClient(main_mod.app)

r = client.post("/api/agent/chat", json={
    "messages": [{"role": "user", "content": "垃圾分类违规怎么处置"}],
    "context": {"sceneName": "智慧园区", "sceneId": "park", "phase": "idle"},
})
assert r.status_code == 200, r.text
d = r.json()
assert "保洁" in d["reply"] or "清理" in d["reply"], f"回复异常: {d}"
# RAG 注入断言：system prompt 应包含知识片段
sys_prompt = CAPTURED.get("system", "")
assert "知识库参考资料" in sys_prompt, "system prompt 未注入知识库块"
assert "垃圾分类违规" in sys_prompt and "拍照取证" in sys_prompt, f"知识片段未注入: {sys_prompt[:200]}"
# 来源标注断言
assert isinstance(d.get("sources"), list) and d["sources"], f"sources 缺失: {d}"
print(f"chat RAG 注入: 通过（sources={d['sources']}）")

# 无关 query 不应注入知识块（或注入空占位）
r2 = client.post("/api/agent/chat", json={
    "messages": [{"role": "user", "content": "你好"}],
    "context": {"phase": "idle"},
})
assert r2.status_code == 200
assert "（无相关内容）" in CAPTURED["system"], "无关 query 不应注入知识内容"
print("无关 query 不误注入: 通过")

print("==== RAG 单测全部通过 ====")
