# -*- coding: utf-8 -*-
"""巡检知识库：本地 RAG 检索增强（零外部依赖，纯标准库）。

- 知识源：knowledge/ 目录下的 Markdown 文件（新增文件重启后端即生效）
- 切块：按 "## " 二级标题切块，超长块按段落续切
- 检索：字符级 bigram + BM25（中文无需分词器/嵌入模型，离线可用）
- 接口：search(query, top_k=2) -> [dict(title, text, source, score)]
"""
from __future__ import annotations

import math
import re
from pathlib import Path

_KB_DIR = Path(__file__).parent / "knowledge"
_K1, _B = 1.5, 0.75          # BM25 经典参数
_MIN_SCORE = 1.5             # 低于此分视为不相关，不注入（检索不误触）
_MAX_CHUNK_CHARS = 500       # 单块正文上限
_SNIPPET_CHARS = 400         # 注入 prompt 时的单块截断长度

# 标点/空白剔除（保留中英文与数字）
_PUNCT = re.compile(r"[\s，。？！、；：“”‘’（）《》〈〉【】·—…～,.\?!;:'\"()<>\[\]{}/\\|`~@#$%^&*+=\u3000]+")

# 查询里的高频虚词 bigram 权重压制（提升实词命中率）
_WEAK = {"的东", "东西", "什么", "怎么", "怎样", "如何", "还是", "以及", "这个", "那个",
         "一下", "是不是", "可以", "请问", "一下下", "应该", "需要", "现在", "时候"}


def _bigrams(text: str) -> list[str]:
    """字符级 bigram：中文检索的零依赖替代方案。"""
    text = _PUNCT.sub("", text)
    grams = [text[i:i + 2] for i in range(len(text) - 1)]
    return [g for g in grams if g not in _WEAK]


def _load_chunks() -> list[dict]:
    chunks: list[dict] = []
    if not _KB_DIR.exists():
        return chunks
    for md in sorted(_KB_DIR.glob("*.md")):
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        # 丢弃一级标题行，按二级标题切块
        text = re.sub(r"^#[^\n]*\n", "", text.lstrip())
        parts = re.split(r"\n(?=## )", text)
        for part in parts:
            if not part.strip():
                continue
            m = re.match(r"##\s*([^\n]+)", part)
            title = m.group(1).strip() if m else md.stem
            body = part[m.end():].strip() if m else part.strip()
            if not body:
                body = title
            # 超长块按空行分段续切
            if len(body) > _MAX_CHUNK_CHARS:
                paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
                blocks, buf = [], ""
                for p in paras:
                    if buf and len(buf) + len(p) > _MAX_CHUNK_CHARS:
                        blocks.append(buf)
                        buf = p
                    else:
                        buf = f"{buf}\n{p}".strip()
                if buf:
                    blocks.append(buf)
            else:
                blocks = [body]
            for i, b in enumerate(blocks, 1):
                label = title if len(blocks) == 1 else f"{title}（{i}/{len(blocks)}）"
                chunks.append({"title": label, "text": b, "source": md.name})
    return chunks


_chunks = _load_chunks()
_df: dict[str, int] = {}
for _c in _chunks:
    _terms = _bigrams(f"{_c['title']} {_c['text']}")
    _c["terms"] = _terms
    _tf: dict[str, int] = {}
    for _t in _terms:
        _tf[_t] = _tf.get(_t, 0) + 1
    _c["tf"] = _tf
    for _t in set(_terms):
        _df[_t] = _df.get(_t, 0) + 1

_N = len(_chunks)
_AVGDL = (sum(len(c["terms"]) for c in _chunks) / _N) if _N else 0.0


def search(query: str, top_k: int = 2, min_score: float = _MIN_SCORE) -> list[dict]:
    """BM25 检索知识块，返回 [{title, text, source, score}]，无相关结果返回空表。"""
    if not _chunks or not _AVGDL:
        return []
    q_terms = _bigrams(query or "")
    if not q_terms:
        return []
    scored = []
    for c in _chunks:
        s = 0.0
        for t in q_terms:
            f = c["tf"].get(t, 0)
            if not f:
                continue
            idf = math.log((_N - _df[t] + 0.5) / (_df[t] + 0.5) + 1.0)
            s += idf * f * (_K1 + 1) / (f + _K1 * (1 - _B + _B * len(c["terms"]) / _AVGDL))
        if s > 0:
            scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    out = []
    for s, c in scored:
        if s < min_score or len(out) >= top_k:
            break
        out.append({
            "title": c["title"],
            "text": c["text"][:_SNIPPET_CHARS],
            "source": c["source"],
            "score": round(s, 2),
        })
    return out


def stats() -> dict:
    """知识库概况（调试/健康检查用）。"""
    return {"chunks": _N, "files": len({c["source"] for c in _chunks}), "avg_len": round(_AVGDL, 1)}
