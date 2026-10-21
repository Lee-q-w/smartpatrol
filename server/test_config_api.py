# -*- coding: utf-8 -*-
"""模型配置 API 单测：页面填 Key → 保存落盘 → 掩码回显 → 试连验证（mock 模型服务）"""
import json
import threading
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import main as main_mod
from main import app

# 配置文件指向临时路径（不碰真实 config.local.json）
TMP_CFG = Path(__file__).parent / ".temp-test-config.json"
main_mod.CONFIG_PATH = TMP_CFG
if TMP_CFG.exists():
    TMP_CFG.unlink()
main_mod.CFG = {}

# ---------- 1. 掩码函数 ----------
assert main_mod._mask_key("") == ""
assert main_mod._mask_key("abc") == "ab****"
assert main_mod._mask_key("sk-abcdef1234567890") == "sk-a****7890"
print("掩码函数: 通过")

# ---------- 2. mock 模型服务 ----------
MOCK_PORT = 18997
MOCK_URL = f"http://127.0.0.1:{MOCK_PORT}/v1"
state = {"status": 200, "body": {"choices": [{"message": {"content": "OK"}}]}}

mock = FastAPI()

@mock.post("/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    assert body["max_tokens"] == 10, "试连应使用最小请求"
    from fastapi.responses import JSONResponse
    if state["status"] == 200:
        return JSONResponse(state["body"], status_code=200)
    return JSONResponse({"error": {"message": "Invalid API key"}}, status_code=state["status"])

server = uvicorn.Server(uvicorn.Config(mock, host="127.0.0.1", port=MOCK_PORT, log_level="warning"))
threading.Thread(target=server.run, daemon=True).start()
time.sleep(1.2)

client = TestClient(app)

# ---------- 3. 初始未配置 ----------
h = client.get("/api/health").json()
assert h["model_configured"] is False
c = client.get("/api/config/model").json()
assert c["configured"] is False and c["apiKeyMasked"] == ""
print("初始未配置: 通过")

# ---------- 4. 保存（试连成功） ----------
state["status"] = 200
r = client.post("/api/config/model", json={
    "baseUrl": MOCK_URL, "apiKey": "sk-test-abcdef1234567890", "model": "test-model",
})
assert r.status_code == 200, r.text
d = r.json()
assert d["ok"] and d["testOk"] and d["configured"]
assert d["apiKeyMasked"] == "sk-t****7890"
# 文件已写入且不进代码库的内容正确
disk = json.loads(TMP_CFG.read_text(encoding="utf-8"))
assert disk["api_key"] == "sk-test-abcdef1234567890"
assert disk["base_url"] == MOCK_URL and disk["model"] == "test-model"
# health 反映已配置
assert client.get("/api/health").json()["model_configured"] is True
# GET 掩码回显（不回传完整 key）
c = client.get("/api/config/model").json()
assert c["configured"] and c["apiKeyMasked"] == "sk-t****7890" and "api_key" not in c
print("保存+试连+落盘+掩码: 通过")

# ---------- 5. 编辑模式：key 留空沿用 ----------
r2 = client.post("/api/config/model", json={
    "baseUrl": MOCK_URL, "apiKey": "", "model": "test-model-v2",
})
assert r2.status_code == 200, r2.text
disk2 = json.loads(TMP_CFG.read_text(encoding="utf-8"))
assert disk2["api_key"] == "sk-test-abcdef1234567890" and disk2["model"] == "test-model-v2"
print("编辑模式 key 沿用: 通过")

# ---------- 6. 试连失败（401）不落盘 ----------
state["status"] = 401
r3 = client.post("/api/config/model", json={
    "baseUrl": MOCK_URL, "apiKey": "sk-wrong-key", "model": "test-model",
})
assert r3.status_code == 400 and "401" in r3.json()["detail"]
disk3 = json.loads(TMP_CFG.read_text(encoding="utf-8"))
assert disk3["api_key"] == "sk-test-abcdef1234567890", "坏 key 不应覆盖好配置"
print("试连失败不落盘: 通过")

# ---------- 7. 参数校验 ----------
r4 = client.post("/api/config/model", json={"baseUrl": "ftp://x", "apiKey": "k", "model": "m"})
assert r4.status_code == 400
r5 = client.post("/api/config/model", json={"baseUrl": MOCK_URL, "apiKey": "k", "model": ""})
assert r5.status_code == 400
print("参数校验: 通过")

# 清理
TMP_CFG.unlink(missing_ok=True)
print("\n==== 模型配置 API 单测全部通过 ====")
