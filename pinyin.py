# -*- coding: utf-8 -*-
"""拼音转换（零第三方依赖）：使用 assets/pinyin.txt（mozillazg/pinyin-data 单字表）。

支持：中文 → 无音调拼音（用于同音容错检索）；拉丁字符原样保留。
"""
import re
from pathlib import Path

_TABLE_PATH = Path(__file__).resolve().parent / "assets" / "pinyin.txt"

# 音调符号 → 基础字母
_TONE_MAP = str.maketrans({
    "ā": "a", "á": "a", "ǎ": "a", "à": "a",
    "ē": "e", "é": "e", "ě": "e", "è": "e", "ê": "e",
    "ī": "i", "í": "i", "ǐ": "i", "ì": "i",
    "ō": "o", "ó": "o", "ǒ": "o", "ò": "o",
    "ū": "u", "ú": "u", "ǔ": "u", "ù": "u",
    "ǖ": "v", "ǘ": "v", "ǚ": "v", "ǜ": "v", "ü": "v",
    "ń": "n", "ň": "n", "": "m", "ḿ": "m",
})

_table = None


def _load_table():
    global _table
    if _table is not None:
        return _table
    t = {}
    if _TABLE_PATH.exists():
        with open(_TABLE_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or not line.startswith("U+"):
                    continue
                try:
                    code, rest = line.split(":", 1)
                    ch = chr(int(code[2:], 16))
                    first = rest.strip().split()[0]
                    t[ch] = first
                except (ValueError, IndexError):
                    continue
    _table = t
    return t


def pinyinize(text):
    """文本 → 小写无音调拼音串（中文逐字拼音拼接，拉丁字符原样小写）。"""
    if not text:
        return ""
    t = _load_table()
    out = []
    for ch in str(text):
        if "\u4e00" <= ch <= "\u9fff":
            py = t.get(ch)
            out.append(py.translate(_TONE_MAP) if py else "")
        else:
            out.append(ch.lower())
    return "".join(out)


def has_latin(text):
    return bool(re.search(r"[a-zA-Z]", text or ""))
