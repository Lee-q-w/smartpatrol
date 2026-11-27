# -*- coding: utf-8 -*-
"""AI 总结单测：降级模板 + PDF 落版"""
import io
import main as main_mod
from report_pdf import build_report_pdf, _fallback_summary
from pypdf import PdfReader

DATA = {
    "sceneName": "智慧园区", "scope": "全园", "mode": "快速巡逻", "source": "仿真引擎",
    "weather": "晴",
    "findings": [
        {"label": "垃圾分类违规", "type": "litter", "near": "bin-3 桶旁", "confidence": 0.9,
         "stage": "confirmed", "handle": {"status": "pending"}, "evidence": "桶旁散落杂物"},
        {"label": "未熄烟头", "type": "cigarette", "near": "bench-3 长椅旁", "confidence": 0.95,
         "stage": "confirmed", "handle": {"status": "resolved"}, "evidence": "长椅旁有烟头"},
        {"label": "垃圾分类违规", "type": "litter", "near": "bin-1 桶旁", "confidence": 0.85,
         "stage": "confirmed", "handle": {"status": "processing"}, "evidence": "垃圾未入桶"},
    ],
}

# 1. 模拟未配置模型 → 降级规则模板
import asyncio
saved_cfg = dict(main_mod.CFG)
main_mod.CFG = {"api_key": "", "base_url": "", "model": "test"}
summ = asyncio.run(main_mod._gen_report_summary(DATA))
assert summ is None, f"未配置模型应返回 None: {summ}"
main_mod.CFG = saved_cfg
print("未配置模型正确降级: 通过")

# 2. 规则模板内容正确
title, text = _fallback_summary(DATA, DATA["findings"])
assert title == "AI 巡检总结与建议"
assert "3 处异常" in text and "垃圾分类违规 2 处" in text, f"统计错误: {text}"
assert "待处理 1 处" in text, f"进度错误: {text}"
print("规则模板统计准确: 通过")

# 3. PDF 落版：总结段存在且在页脚声明之前
pdf = build_report_pdf(dict(DATA))
pages = PdfReader(io.BytesIO(pdf)).pages
full = "\n".join(p.extract_text() for p in pages)
assert "AI 巡检总结与建议" in full, "PDF 缺少总结标题"
assert "本轮共发现 3 处异常" in full, "PDF 缺少总结正文"
assert full.find("AI 巡检总结与建议") < full.find("说明：标注"), "总结段应在页脚声明之前"
print("PDF 总结段落版: 通过")

# 4. 雨天报告点明环境
title2, text2 = _fallback_summary(dict(DATA, weather="大雨"), DATA["findings"])
assert "大雨" in text2, "雨天总结应点明环境"
print("雨天总结点明环境: 通过")

print("==== 报告 AI 总结单测全部通过 ====")