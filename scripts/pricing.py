"""本地价格表（data/pricing.json），不联网。"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, Optional, Tuple

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "data", "pricing.json")
_TABLE: Optional[dict] = None


def table() -> dict:
    global _TABLE
    if _TABLE is None:
        with open(_PATH, encoding="utf-8") as fh:
            _TABLE = json.load(fh)
    return _TABLE


def _norm(model: str) -> str:
    m = model.lower().strip()
    m = re.sub(r"^(?:anthropic|openai)[/.]", "", m)
    m = re.sub(r"-\d{8}$", "", m)          # claude-sonnet-4-5-20250929
    m = re.sub(r"\[.*?\]$", "", m)         # claude-opus-4-6[1m]
    return m


def lookup(model: Optional[str]) -> Tuple[Optional[Dict[str, float]], bool]:
    """返回 (单价 dict, 是否精确命中)。完全未知返回 (None, False)。"""
    if not model:
        return None, False
    t = table()
    m = _norm(model)
    m = t["aliases"].get(m, m)
    if m in t["models"]:
        return t["models"][m], m == _norm(model)
    # 前缀匹配：取最长的已知 key（例如 gpt-5.3-codex-high）
    keys = sorted((k for k in t["models"] if m.startswith(k)), key=len, reverse=True)
    if keys:
        return t["models"][keys[0]], False
    for prefix, target in t["family_fallback"].items():
        if m.startswith(prefix) or prefix in m:
            return t["models"][target], False
    return None, False


def cost(tokens: Dict[str, int], model: Optional[str]) -> Tuple[float, bool, bool]:
    """返回 (美元, 是否精确命中, 是否有价格)。reasoning 已含在 output 里，不重复计。"""
    price, exact = lookup(model)
    if price is None:
        return 0.0, False, False
    c = (tokens.get("input", 0) * price["input"]
         + tokens.get("output", 0) * price["output"]
         + tokens.get("cache_read", 0) * price.get("cache_read", price["input"])
         + tokens.get("cache_write", 0) * price.get("cache_write", price["input"])) / 1e6
    return c, exact, True
