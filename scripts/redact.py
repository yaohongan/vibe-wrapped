"""原话脱敏与项目名隐藏。"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

_PATTERNS = [
    re.compile(r"https?://\S+", re.I),                                  # URL
    re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"),                        # 邮箱
    re.compile(r"(?:~|[A-Za-z]:)?(?:/|\\)[\w.@\-+ ]+(?:(?:/|\\)[\w.@\-+]+)+"),  # 路径
    re.compile(r"\b(?:sk|pk|rk|ghp|gho|ghs|github_pat|xox[abp]|AKIA|AIza)[-_A-Za-z0-9]{8,}\b"),  # 密钥
    re.compile(r"\b[0-9a-fA-F]{24,}\b"),                                # 长 hex
    re.compile(r"\b[A-Za-z0-9+/_\-]{32,}={0,2}"),                       # 长 base64/token
    re.compile(r"\d[\d\- ]{8,}\d"),                                     # 长数字（手机/卡号）
]


def redact_text(text: str) -> str:
    for p in _PATTERNS:
        text = p.sub("***", text)
    return text


def truncate(text: str, limit: int = 30) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def anonymize_projects(names: List[str]) -> Dict[str, str]:
    """按出现顺序映射为 项目 A / B / C…"""
    out = {}
    for i, n in enumerate(names):
        out[n] = "项目 " + (chr(ord("A") + i) if i < 26 else str(i + 1))
    return out


def file_label(path: str, hide: bool) -> str:
    base = path.replace("\\", "/").rstrip("/").split("/")[-1] or path
    if not hide:
        return base
    if "." in base.strip("."):
        return "*." + base.rsplit(".", 1)[-1]
    return "*"
