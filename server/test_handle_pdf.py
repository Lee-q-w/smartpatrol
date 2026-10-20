# 工单闭环 PDF 验证：含 handle 字段的报告 → 提取文本断言"处置进度/已处置"
import base64
import io

from PIL import Image as PILImage
from pypdf import PdfReader

from report_pdf import build_report_pdf

# 8x6 红色 JPEG（Pillow 生成，可靠）
_buf = io.BytesIO()
PILImage.new("RGB", (8, 6), "#c0392b").save(_buf, format="JPEG", quality=80)
_JPEG_B64 = base64.b64encode(_buf.getvalue()).decode()

data = {
    "sceneName": "园区场景",
    "scope": "全园",
    "mode": "快速巡逻",
    "source": "仿真引擎",
    "findings": [
        {
            "label": "垃圾分类违规", "type": "litter", "near": "3号垃圾桶", "confidence": 0.93,
            "stage": "confirmed", "evidence": "垃圾桶旁散落杂物", "source": "ai",
            "photoB64": _JPEG_B64,
            "handle": {"status": "resolved", "note": "保洁已清理", "at": 1},
        },
        {
            "label": "未熄烟头", "type": "cigarette", "near": "3号长椅", "confidence": 0.88,
            "stage": "confirmed", "evidence": "长椅旁两处烟头", "source": "real-ai",
            "handle": {"status": "processing"},
        },
        {
            "label": "植被缺水", "type": "dry", "near": "西南草坪", "confidence": 0.9,
            "stage": "detected", "evidence": "草坪发黄", "source": "sim",
            "handle": {"status": "pending"},
        },
    ],
}
pdf = build_report_pdf(data)
assert pdf[:4] == b"%PDF", "PDF 魔数错误"

text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf)).pages)
checks = {
    "处置进度元信息": "处置进度" in text and "已处置 1 处" in text,
    "处置中统计": "处理中 1 处" in text,
    "待处理统计": "待处理 1 处" in text,
    "工单备注": "保洁已清理" in text,
    "真机实拍来源": "真机实拍" in text,
}
fails = [k for k, ok in checks.items() if not ok]
for k, ok in checks.items():
    print(("PASS" if ok else "FAIL"), k)
assert not fails, f"失败: {fails}"
print(f"==== 工单 PDF 验证全部通过（{len(pdf)} 字节）====")
