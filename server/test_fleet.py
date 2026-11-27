# -*- coding: utf-8 -*-
"""双车协同单测：意图解析 + 车队参数"""
import main as main_mod

ctx = {"sceneId": "park", "sceneName": "智慧园区", "mode": "sim", "phase": "idle",
       "weather": "clear", "zones": [{"id": "zone-a", "name": "西北分区"}], "anomalies": []}

dual = ["叫两台车分头查全园", "双车协同巡逻一圈", "让两台车并行巡检"]
for q in dual:
    acts = main_mod._local_fallback_actions(q, ctx)
    patrol = next((a for a in acts if a["type"] == "patrol"), None)
    assert patrol and patrol["args"].get("fleet") == 2, f"{q} 未识别双车意图: {acts}"
print("双车意图识别: 通过（3 组说法）")

single = ["帮我巡逻一圈", "去西南分区详查"]
for q in single:
    acts = main_mod._local_fallback_actions(q, ctx)
    patrol = next((a for a in acts if a["type"] == "patrol"), None)
    assert patrol and "fleet" not in patrol["args"], f"{q} 不应触发双车: {acts}"
print("单车意图不误触: 通过")

# 提示词须告知模型 fleet 能力（否则模型会答"没法派两台车"）
assert "fleet" in main_mod.AGENT_SYSTEM_PROMPT and "fleet" in main_mod.STREAM_SYSTEM_PROMPT
print("提示词含车队能力: 通过")

print("==== 双车协同单测全部通过 ====")