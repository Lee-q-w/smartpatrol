# -*- coding: utf-8 -*-
"""雨天自适应模式单测：上下文约束 / 规则引擎降级 / 报告环境标注 / 积水类型"""
import io
import main as main_mod
from report_pdf import build_report_pdf
from pypdf import PdfReader

# ---------- 1. 上下文块注入天气约束 ----------
ctx_storm = {"sceneId": "park", "sceneName": "智慧园区", "mode": "sim", "phase": "idle",
             "patrolMode": "quick", "zones": [{"id": "zone-c", "name": "西南分区"}],
             "weather": "storm", "weatherLabel": "大雨", "anomalies": []}
block = main_mod._build_context_block(ctx_storm)
assert "作业环境：大雨" in block, f"缺作业环境行: {block[:200]}"
assert "无人机无法起飞" in block and "禁止 recheck" in block, f"缺大雨约束: {block}"
# 判定项口径：雨天不是降低精度，而是判定项启停
assert "不判 dry" in block and "不判 cigarette" in block, f"缺大雨判定项启停: {block}"
assert "waterlogging" in block, f"大雨应启用积水内涝: {block}"
print("上下文天气约束: 通过")

ctx_clear = dict(ctx_storm, weather="clear")
block_clear = main_mod._build_context_block(ctx_clear)
assert "作业环境：晴" in block_clear and "禁止 recheck" not in block_clear
print("晴天无额外约束: 通过")

# 小雨：烟头收窄到遮蔽空间，不判缺水
block_rain = main_mod._build_context_block(dict(ctx_storm, weather="rain"))
assert "雨棚" in block_rain and "不判 dry" in block_rain, f"小雨口径异常: {block_rain}"
assert "禁止 recheck" not in block_rain, "小雨不应禁用复核"
print("小雨判定项收窄: 通过（烟头仅遮蔽处）")

# ---------- 2. 规则引擎：大雨不下发无人机复核 ----------
act_storm = main_mod._local_fallback_actions("帮我复核一遍", ctx_storm)
assert not any(a["type"] == "recheck" for a in act_storm), f"大雨仍下发 recheck: {act_storm}"
act_clear = main_mod._local_fallback_actions("帮我复核一遍", ctx_clear)
assert any(a["type"] == "recheck" for a in act_clear), f"晴天应可复核: {act_clear}"
print("大雨拦截无人机复核: 通过（晴天仍可复核）")

# 大雨仍允许发起巡逻（车可低速跑关键点）
act_patrol = main_mod._local_fallback_actions("去西南分区巡检一下", ctx_storm)
assert any(a["type"] == "patrol" for a in act_patrol), f"大雨不应拦截巡逻: {act_patrol}"
print("大雨保留地面巡逻: 通过")

# ---------- 3. 报告记录作业环境与降级说明 ----------
pdf = build_report_pdf({
    "sceneName": "智慧园区", "scope": "全园", "mode": "快速巡逻", "source": "仿真引擎",
    "weather": "大雨", "weatherNote": "大雨：无人机复核暂停，植被类点位跳过，优先通道占用与积水内涝",
    "findings": [{"label": "积水内涝", "type": "waterlogging", "near": "zone-c", "confidence": 0.9,
                  "stage": "detected", "handle": {"status": "pending"}, "evidence": "路面成片积水，淹及标线"}],
})
text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
for key in ("作业环境", "大雨", "环境降级", "积水内涝"):
    assert key in text, f"报告缺少「{key}」: {text[:400]}"
print("报告环境标注: 通过（作业环境 / 环境降级 / 积水异常）")

# ---------- 4. 积水内涝类型可识别 ----------
assert "waterlogging" in main_mod.SYSTEM_PROMPT, "识别提示词缺积水类型"
assert main_mod.TYPE_ALIASES.get("waterlogging"), "缺积水别名映射"
assert "绿地积水" in main_mod.SYSTEM_PROMPT, "积水判定应覆盖绿地积水"
assert "不得判为 dry" in main_mod.SYSTEM_PROMPT, "识别提示词应禁止雨天判缺水"
print("积水内涝类型: 通过（含绿地积水 / 雨天禁判缺水）")

# ---------- 5. 大雨复核短路（不调模型，直接给降级话术） ----------
g = main_mod._storm_recheck_guard("帮我把异常复核一下", ctx_storm)
assert g and "无人机" in g and "人工" in g, f"大雨应短路复核: {g}"
assert main_mod._storm_recheck_guard("帮我把异常复核一下", ctx_clear) is None, "晴天不应短路"
assert main_mod._storm_recheck_guard("现在有什么异常", ctx_storm) is None, "非复核请求不应短路"
print("大雨复核短路: 通过")

print("==== 雨天自适应单测全部通过 ====")