# -*- coding: utf-8 -*-
"""热点单测：意图 + 统计聚合（纯函数部分）"""
import main as main_mod

ctx = {"sceneId": "park", "sceneName": "智慧园区", "mode": "sim", "phase": "idle",
       "weather": "clear", "zones": [{"id": "zone-a", "name": "西北分区"}], "anomalies": []}

# 1. 热点意图：定点 + hotspot 标记
for q in ["去热点点位复查", "查一下高频点位", "热点先看一下"]:
    acts = main_mod._local_fallback_actions(q, ctx)
    patrol = next((a for a in acts if a["type"] == "patrol"), None)
    assert patrol and patrol["args"].get("hotspot") is True, f"{q} 未识别热点意图: {acts}"
    assert patrol["args"].get("mode") == "point", f"{q} 热点应走定点详查: {acts}"
    assert not any(a["type"] == "recheck" for a in acts), f"{q} 不应误触发无人机复核: {acts}"
print("热点意图识别: 通过")

# 2. 普通复查仍触发无人机复核
acts = main_mod._local_fallback_actions("帮我复核一遍", ctx)
assert any(a["type"] == "recheck" for a in acts), f"普通复查应触发复核: {acts}"
print("普通复查不误伤: 通过")

# 3. 提示词声明热点能力
assert "hotspot" in main_mod.AGENT_SYSTEM_PROMPT and "热点" in main_mod.STREAM_SYSTEM_PROMPT
print("提示词含热点能力: 通过")

print("==== 热点自适应单测全部通过 ====")