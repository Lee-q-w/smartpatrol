# -*- coding: utf-8 -*-
"""巡检报告 PDF 生成（reportlab）"""
import io
from datetime import datetime
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

# ---------- 中文字体注册（Windows 系统字体，缺失则回退内置） ----------
_FONT = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
_FONT_READY = False


def register_cn_font() -> None:
    global _FONT, _FONT_BOLD, _FONT_READY
    if _FONT_READY:
        return
    candidates = [
        ("SimHei", r"C:\Windows\Fonts\simhei.ttf"),
        ("MSYaHei", r"C:\Windows\Fonts\msyh.ttc"),
        ("SimSun", r"C:\Windows\Fonts\simsun.ttc"),
        # Linux（GitHub Actions / Noto CJK / 文泉驿）
        ("NotoCJK", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        ("WenQuanYi", "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    ]
    for name, path in candidates:
        try:
            if not Path(path).exists():
                continue
            pdfmetrics.registerFont(TTFont(name, path))
            _FONT, _FONT_BOLD, _FONT_READY = name, name, True
            return
        except Exception:
            continue
    _FONT_READY = True  # 回退内置字体（中文将不可显示，但不崩溃）


# ---------- 样式 ----------
def styles():
    return {
        "title": ParagraphStyle("title", fontName=_FONT_BOLD, fontSize=20, leading=26,
                                alignment=1, spaceAfter=4, textColor=colors.HexColor("#1f2d3d")),
        "subtitle": ParagraphStyle("subtitle", fontName=_FONT, fontSize=10, leading=14,
                                   alignment=1, textColor=colors.HexColor("#909399"), spaceAfter=10),
        "h2": ParagraphStyle("h2", fontName=_FONT_BOLD, fontSize=13, leading=18,
                             spaceBefore=10, spaceAfter=6, textColor=colors.HexColor("#2c5f8a")),
        "body": ParagraphStyle("body", fontName=_FONT, fontSize=10, leading=15),
        "meta": ParagraphStyle("meta", fontName=_FONT, fontSize=9, leading=13,
                               textColor=colors.HexColor("#606266")),
        "evi": ParagraphStyle("evi", fontName=_FONT, fontSize=9, leading=13.5,
                              textColor=colors.HexColor("#606266")),
        "cap": ParagraphStyle("cap", fontName=_FONT, fontSize=8.5, leading=12,
                              alignment=1, textColor=colors.HexColor("#909399"), spaceBefore=2),
    }


def _esc(s) -> str:
    return (str(s) if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _photo_flowable(photo_b64: str, max_w=80 * mm, max_h=52 * mm):
    """base64 JPEG/PNG 照片 → 等比缩放 Image 流；失败返回 None"""
    if not photo_b64:
        return None
    try:
        import base64
        raw = base64.b64decode(photo_b64)
        img = PILImage.open(io.BytesIO(raw))
        w, h = img.size
        k = min(max_w / w, max_h / h, 1.0)
        buf = io.BytesIO()
        fmt = "JPEG" if img.mode in ("RGB", "L") else "PNG"
        if fmt == "JPEG":
            img = img.convert("RGB")
        img.save(buf, format=fmt)
        buf.seek(0)
        return Image(buf, width=w * k, height=h * k)
    except Exception:
        return None


def build_report_pdf(data: dict) -> bytes:
    """
    data: {
      sceneName, scope, mode, source,        # 元信息
      findings: [                            # 异常清单
        { label, type, near, confidence, stage, evidence, source,
          photoB64, photoTitle, photoDesc, droneB64 }
      ],
    }
    返回 PDF 字节流。
    """
    register_cn_font()
    S = styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title="智巡 SmartPatrol 巡检报告")
    flow = []

    # ---- 标题区 ----
    flow.append(Paragraph("智巡 SmartPatrol · 巡检报告", S["title"]))
    flow.append(Paragraph("虚实结合的园区智能巡检平台 —— 仿真推演 · 真实回放 · 真图识别", S["subtitle"]))

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    findings_all = data.get("findings", [])
    confirmed = [f for f in findings_all if f.get("stage") == "confirmed"]
    n_resolved = sum(1 for f in findings_all if (f.get("handle") or {}).get("status") == "resolved")
    n_processing = sum(1 for f in findings_all if (f.get("handle") or {}).get("status") == "processing")
    meta_rows = [
        ["巡检场景", _esc(data.get("sceneName", "—"))],
        ["巡检范围", _esc(data.get("scope", "—"))],
        ["巡查方式", _esc(data.get("mode", "—"))],
        ["数据来源", _esc(data.get("source", "—"))],
        ["发现异常", f"{len(findings_all)} 处（其中 {len(confirmed)} 处已复核确认）"],
        ["处置进度", f"已处置 {n_resolved} 处 · 处理中 {n_processing} 处 · 待处理 {len(findings_all) - n_resolved - n_processing} 处"],
        ["生成时间", now],
    ]
    meta_tbl = Table([[Paragraph(f"<b>{k}</b>", S["meta"]), Paragraph(v, S["meta"])] for k, v in meta_rows],
                     colWidths=[28 * mm, 140 * mm])
    meta_tbl.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#f5f8fb"), colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dcdfe6")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    flow.append(meta_tbl)

    # ---- 异常清单 ----
    findings = findings_all
    if not findings:
        flow.append(Spacer(1, 8 * mm))
        flow.append(Paragraph("本次巡逻未发现异常。", ParagraphStyle(
            "empty", parent=S["body"], alignment=1, textColor=colors.HexColor("#67c23a"), fontSize=12)))
    else:
        for i, f in enumerate(findings, 1):
            flow.append(Spacer(1, 5 * mm))
            # 分隔线
            sep = Table([[""]], colWidths=[168 * mm], rowHeights=[0.6])
            sep.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e4e9f0"))]))
            flow.append(sep)
            flow.append(Spacer(1, 2 * mm))
            src = f.get("source", "sim")
            src_label = {"ai": "真图识别（AI 判读）", "sim": "仿真推演", "replay": "真实回放记录",
                         "real-ai": "真机实拍（AI 判读）"}.get(src, src)
            head = f"异常 {i}｜{f.get('label', '—')}"
            flow.append(Paragraph(f"<b>{_esc(head)}</b>", S["h2"]))

            try:
                conf = round(float(f.get("confidence", 0) or 0) * 100)
            except (TypeError, ValueError):
                conf = 0
            stage = f.get("stage", "detected")
            stage_label = {"detected": "初步判断（待复核）", "rechecking": "复核中", "confirmed": "已复核确认"}.get(stage, stage)
            hst = (f.get("handle") or {}).get("status", "pending")
            handle_label = {"pending": "未处理", "processing": "处理中", "resolved": "已处置完成"}.get(hst, hst)
            handle_note = (f.get("handle") or {}).get("note", "")
            rows = [
                ("异常类型", f"{f.get('label', '—')}（{f.get('type', '—')}）"),
                ("位置", f.get("near", "—")),
                ("把握程度", f"{conf}%"),
                ("复核状态", stage_label),
                ("处置进度", handle_label + (f"（{handle_note}）" if handle_note else "")),
                ("证据来源", src_label),
            ]
            tbl = Table([[Paragraph(f"<b>{k}</b>", S["meta"]), Paragraph(_esc(v), S["meta"])] for k, v in rows],
                        colWidths=[28 * mm, 140 * mm])
            tbl.setStyle(TableStyle([
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#fafcfe"), colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e4e9f0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]))
            flow.append(tbl)

            if f.get("evidence"):
                flow.append(Spacer(1, 1.5 * mm))
                flow.append(Paragraph(f"证据描述：{_esc(f['evidence'])}", S["evi"]))

            # 证据照片（近景 + 无人机复核，双列）
            photos = []
            p1 = _photo_flowable(f.get("photoB64"))
            if p1:
                photos.append((p1, f.get("photoTitle") or "近景检查帧"))
            p2 = _photo_flowable(f.get("droneB64"))
            if p2:
                photos.append((p2, "无人机俯拍复核帧"))
            if photos:
                cells, caps = [], []
                for img, cap in photos:
                    cells.append(img)
                    caps.append(Paragraph(_esc(cap), S["cap"]))
                w = 80 * mm if len(photos) == 1 else 79 * mm
                photo_tbl = Table([cells, caps], colWidths=[w] * len(photos))
                photo_tbl.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                ]))
                flow.append(Spacer(1, 2 * mm))
                flow.append(photo_tbl)

    # ---- 页脚声明 ----
    flow.append(Spacer(1, 8 * mm))
    foot = ParagraphStyle("foot", parent=S["cap"], fontSize=8)
    flow.append(Paragraph(
        "说明：标注「真图识别」的异常来自上传的真实照片经多模态大模型判读（AI 识别中心回填）；"
        "「真机实拍」异常来自巡检设备摄像头实时回传画面经 AI 判读；"
        "「仿真推演」异常来自巡检仿真引擎（seed=2026 真值）；「真实回放」异常来自省赛实测记录。"
        "工单处置进度由巡检人员在平台端实时更新。模型 Key 仅保存在本地配置文件，不随报告外发。", foot))

    doc.build(flow)
    return buf.getvalue()
