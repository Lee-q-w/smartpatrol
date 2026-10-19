# -*- coding: utf-8 -*-
"""识别链路单测：mock 一个 OpenAI 兼容模型服务，验证 /api/recognize 全链路"""
import base64
import json
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient
import uvicorn
import httpx
from main import app, parse_model_output

# ---------- 1. parse_model_output 单测 ----------
cases = [
    ('{"found": true, "type": "litter", "label": "垃圾分类违规", "confidence": 0.92, "evidence": "桶旁散落垃圾"}',
     dict(found=True, type="litter", confidence=0.92)),
    ('```json\n{"found": true, "type": "垃圾散落", "label": "x", "confidence": 88, "evidence": "y"}\n```',
     dict(found=True, type="litter", confidence=0.88)),          # 中文类型 + 88→0.88
    ('前置说明文字 {"found": true, "type": "dry", "confidence": 1.4, "evidence": "z"} 后缀说明',
     dict(found=True, type="dry", confidence=1.0)),              # 超界钳制
    ('{"found": false, "type": null, "label": null, "confidence": 0, "evidence": "无"}',
     dict(found=False, type=None)),
    ('模型故障没有 JSON', dict(found=False, confidence=0)),
]
for text, expect in cases:
    r = parse_model_output(text)
    for k, v in expect.items():
        assert r[k] == v, f"{text[:30]}… 的 {k} 应为 {v}，实际 {r[k]}"
print(f"parse_model_output: {len(cases)}/{len(cases)} 通过")

# ---------- 2. mock 模型服务 ----------
MOCK_PORT = 18999
MOCK_URL = f"http://127.0.0.1:{MOCK_PORT}/v1"

from fastapi import FastAPI, Request
mock = FastAPI()

@mock.post("/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    assert body["model"] == "test-model"
    # 校验图片真的带上了（base64 非空）
    content = body["messages"][1]["content"]
    img_part = [c for c in content if c.get("type") == "image_url"][0]
    assert img_part["image_url"]["url"].startswith("data:image/jpeg;base64,") and len(img_part["image_url"]["url"]) > 100
    return {"choices": [{"message": {"content": '{"found": true, "type": "cigarette", "label": "未熄烟头", "confidence": 0.97, "evidence": "地面有两处橙红色亮点"}'}}]}

server = uvicorn.Server(uvicorn.Config(mock, host="127.0.0.1", port=MOCK_PORT, log_level="warning"))
t = threading.Thread(target=server.run, daemon=True)
t.start()
time.sleep(1.2)

# ---------- 3. 注入配置并全链路测试 ----------
import main as main_mod
main_mod.CFG = {"base_url": MOCK_URL, "api_key": "test-key", "model": "test-model"}

client = TestClient(app)
# 1x1 红色 PNG
png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
png = base64.b64decode(png_b64)

r = client.post("/api/recognize", files={"file": ("frame.png", png, "image/png")})
assert r.status_code == 200, r.text
data = r.json()
assert data["found"] is True
assert data["type"] == "cigarette"
assert data["confidence"] == 0.97
assert "橙红色" in data["evidence"]
assert data["raw"]
print(f"全链路识别: 通过（{data['label']} 置信 {data['confidence']}）")

# 空文件 400
r2 = client.post("/api/recognize", files={"file": ("empty.png", b"", "image/png")})
assert r2.status_code == 400
print("空文件 400: 通过")

# 健康检查反映配置
h = client.get("/api/health").json()
assert h["model_configured"] is True and h["model"] == "test-model"
print("健康检查: 通过")
print("\n==== 全部通过 ====")