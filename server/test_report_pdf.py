# -*- coding: utf-8 -*-
"""报告导出 PDF 单测"""
import base64
import io

from report_pdf import build_report_pdf, register_cn_font

# ---------- 1. 中文字体注册 ----------
register_cn_font()
from report_pdf import _FONT
assert _FONT != "Helvetica", "中文字体未注册成功"
print(f"中文字体注册: 通过（{_FONT}）")

# ---------- 2. 生成 1x1 测试照片（PNG） ----------
from PIL import Image as PILImage
buf = io.BytesIO()
PILImage.new("RGB", (60, 40), (230, 120, 60)).save(buf, format="JPEG")
photo_b64 = base64.b64encode(buf.getvalue()).decode()
print("测试照片构造: 通过")

# ---------- 3. 完整报告（3 异常 + 2 照片） ----------
data = {
    "sceneName": "智慧园区",
    "scope": "西南分区",
    "mode": "快速巡逻",
    "source": "仿真模式（seed=2026）",
    "findings": [
        {
            "label": "未熄烟头", "type": "cigarette", "near": "bench-3 长椅旁",
            "confidence": 0.98, "stage": "confirmed", "source": "sim",
            "evidence": "橙色亮点 2 处（长椅步道边缘 + 步道中段），无人机俯拍复核确认",
            "photoB64": photo_b64, "photoTitle": "AGV 近景检查帧（bench-3）",
            "photoDesc": "长椅旁步道上可见两处橙红色亮点",
            "droneB64": photo_b64,
        },
        {
            "label": "植被缺水", "type": "dry", "near": "lawn-sw 草坪",
            "confidence": 0.95, "stage": "confirmed", "source": "sim",
            "evidence": "草坪内黄褐斑驳斑块，复核确认",
        },
        {
            "label": "未熄烟头（真图）", "type": "cigarette", "near": "人工标注（智慧园区）",
            "confidence": 0.97, "stage": "confirmed", "source": "ai",
            "evidence": "真图识别：地面有两处橙红色亮点",
            "photoB64": photo_b64, "photoTitle": "AI 识别证据帧",
        },
    ],
}
pdf = build_report_pdf(data)
assert pdf[:4] == b"%PDF", "非 PDF 魔数"
assert len(pdf) > 15000, f"PDF 过小（{len(pdf)} 字节），疑似缺照片"
print(f"完整报告 PDF: 通过（{len(pdf) // 1024} KB，3 异常 + 3 照片）")

# ---------- 4. 空报告 ----------
empty = build_report_pdf({"sceneName": "室内仓库", "scope": "A 存储区", "mode": "定点详查",
                          "source": "仿真模式", "findings": []})
assert empty[:4] == b"%PDF" and b"%%EOF" in empty[-64:]
print(f"空报告 PDF: 通过（{len(empty)} 字节）")

# ---------- 5. 恶意/容错数据 ----------
bad = build_report_pdf({"sceneName": "<script>x</script>", "findings": [
    {"label": "垃圾&分类", "type": "litter", "near": None, "confidence": "oops",
     "stage": "weird", "evidence": None, "photoB64": "!!!not-base64!!!"},
]})
assert bad[:4] == b"%PDF"
print(f"容错数据 PDF: 通过（坏照片/坏置信度/HTML 注入字符均不崩溃）")

print("\n==== 报告导出单测全部通过 ====")