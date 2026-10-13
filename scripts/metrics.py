"""Event 列表 → metrics dict。纯函数：同样的输入，同样的输出。

约定：
- 用户行为指标（作息/脾气/依赖度）只算非子代理的 user_msg。
- 花费指标计入子代理。
- 所有时间转本地时区后再统计；0:00–5:59 视为“前一天的延续”只用于“最晚一次”。
"""
from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, tzinfo
from typing import Dict, Iterable, List, Optional, Tuple

import pricing
import redact

LEX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lexicon")
GAP = timedelta(hours=2)                 # 会话内空档超过 2 小时视为断开
SHORT_LEN = 10                           # ≤10 字算短指令
QUOTE_LIMIT = 30
USER_CHAR_CAP = 500                      # 单条用户消息字数按此封顶，避免粘贴文档拉高均值
LONG_PASTE = 300                         # 超过这个长度的消息多半是粘贴文档，不参与脾气判定

CONTINUE_WORDS = {
    "继续", "继续吧", "继续做", "继续做吧", "接着", "接着来", "go", "go on", "continue",
    "keep going", "proceed", "ok", "okay", "好", "好的", "行", "可以", "确认", "是", "y",
    "yes", "要", "嗯", "嗯嗯", "对", "go ahead", "do it",
}
POLITE_RE = re.compile(r"谢谢|感谢|辛苦|麻烦|please|thanks|thank you|thx|\bty\b", re.I)
CAPS_RE = re.compile(r"\b[A-Z]{3,}\b")
PUNCT_RE = re.compile(r"[!！]{2,}|[?？]{2,}")
QQQ_RE = re.compile(r"[?？]{2,}")


# ───────────── 词典 ─────────────
def load_lexicon() -> Tuple[List[Tuple[str, int]], List[Tuple[re.Pattern, int]]]:
    zh: List[Tuple[str, int]] = []
    en: List[Tuple[re.Pattern, int]] = []
    for fn, is_en in (("angry_zh.txt", False), ("angry_en.txt", True)):
        with open(os.path.join(LEX_DIR, fn), encoding="utf-8") as fh:
            for raw in fh:
                line = raw.rstrip("\n")
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                word, _, w = line.partition("\t")
                weight = int(w) if w.strip().isdigit() else 1
                word = word.strip()
                if not is_en:
                    zh.append((word, weight))
                    continue
                if word.startswith("^"):
                    w_ = re.escape(word[1:].lower())
                    # 只在开头，或后面紧跟标点/结尾（单独成句）时命中
                    pat = re.compile(r"^\s*" + w_ + r"(?=$|[,.!?;:，。！？…])", re.I)
                else:
                    pat = re.compile(r"(?<![A-Za-z])" + re.escape(word.lower()) + r"(?![A-Za-z])", re.I)
                en.append((pat, weight))
    return zh, en


def anger_score(text: str, lex) -> int:
    """0 = 不暴躁；>0 为强度。每条最多算一次命中，强度累加额外项。"""
    if len(text) > LONG_PASTE:
        return 0
    zh, en = lex
    base = 0
    for w, wt in zh:
        if w in text:
            base = max(base, wt)
    for pat, wt in en:
        if pat.search(text):
            base = max(base, wt)
    if QQQ_RE.search(text) and base == 0:
        base = 1
    if base == 0:
        return 0
    score = base
    if CAPS_RE.search(text):
        score += 1
    if PUNCT_RE.search(text):
        score += 1
    return score


# ───────────── 工具 ─────────────
def _local(ts: datetime, tz: Optional[tzinfo]) -> datetime:
    return ts.astimezone(tz) if tz else ts.astimezone()


def _night_key(dt: datetime) -> int:
    """“最晚”排序键：0:00–5:59 视为前一天延续，排在 23:59 之后。"""
    h = dt.hour + (24 if dt.hour < 6 else 0)
    return h * 60 + dt.minute


def _fmt_dur(td: timedelta) -> str:
    m = int(td.total_seconds() // 60)
    return f"{m // 60}小时{m % 60:02d}分" if m >= 60 else f"{m}分钟"


def _ratio(a: float, b: float) -> float:
    return a / b if b else 0.0


def _longest_streak(days: Iterable[date]) -> int:
    ds = sorted(set(days))
    best = cur = 0
    prev = None
    for d in ds:
        cur = cur + 1 if prev and d - prev == timedelta(days=1) else 1
        best = max(best, cur)
        prev = d
    return best


TOOL_LABEL = {"edit": "改文件", "run": "跑命令", "read": "读文件", "search": "搜索"}


# ───────────── 主函数 ─────────────
def compute(events: List, tz: Optional[tzinfo] = None,
            since: Optional[date] = None, until: Optional[date] = None,
            hide_projects: bool = False, hide_files: Optional[bool] = None,
            lex=None) -> dict:
    lex = lex or load_lexicon()
    hide_files = hide_projects if hide_files is None else hide_files

    ev = []
    for e in events:
        ld = _local(e.ts, tz)
        d = ld.date()
        if since and d < since:
            continue
        if until and d > until:
            continue
        ev.append((ld, e))
    ev.sort(key=lambda x: (x[0], x[1].platform, x[1].raw_ref))

    platforms = sorted({e.platform for _, e in ev})
    users = [(ld, e) for ld, e in ev if e.kind == "user_msg" and not e.is_subagent]
    n_user = len(users)

    # ── 作息 ──
    hours = [0] * 24
    for ld, _ in users:
        hours[ld.hour] += 1
    small = sum(hours[0:5])
    weekend = sum(1 for ld, _ in users if ld.weekday() >= 5)
    per_day = Counter(ld.date() for ld, _ in users)
    busiest = None
    if per_day:
        d, n = sorted(per_day.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        busiest = {"date": d.isoformat(), "count": n}
    latest = None
    if users:
        ld, e = sorted(users, key=lambda x: (-_night_key(x[0]), x[0]))[0]
        latest = {"time": ld.strftime("%H:%M"), "date": ld.date().isoformat(),
                  "hour": ld.hour, "is_after_midnight": ld.hour < 6}
    first_day = min(per_day) if per_day else None
    last_day = max(per_day) if per_day else None

    rhythm = {
        "night_ratio": _ratio(small, n_user),
        "weekend_ratio": _ratio(weekend, n_user),
        "latest": latest,
        "busiest_day": busiest,
        "active_days": len(per_day),
        "longest_streak": _longest_streak(per_day.keys()),
        "hours": hours,
        "daily": {d.isoformat(): n for d, n in sorted(per_day.items())},
        "first_day": first_day.isoformat() if first_day else None,
        "last_day": last_day.isoformat() if last_day else None,
    }

    # ── 脾气 ──
    scored = [(anger_score(e.text or "", lex), ld, e) for ld, e in users]
    hits = [s for s in scored if s[0] > 0]
    quote = None
    if hits:
        s, ld, e = sorted(hits, key=lambda x: (-x[0], len(x[2].text), x[1]))[0]
        quote = {"raw": e.text, "strength": s, "date": ld.date().isoformat(),
                 "platform": e.platform}
    interrupts = sum(1 for ld, e in ev if e.kind == "interrupt" and not e.is_subagent)
    temper = {
        "angry_rate": _ratio(len(hits), n_user),
        "angry_count": len(hits),
        "strength_total": sum(s[0] for s in hits),
        "quote": quote,
        "interrupts": interrupts,
        "polite_count": sum(1 for ld, e in users if POLITE_RE.search(e.text or "")),
    }

    # ── 依赖度 ──
    user_chars = sum(min(e.n_chars, USER_CHAR_CAP) for _, e in users)
    ai = [e for ld, e in ev if e.kind == "ai_msg" and not e.is_subagent]
    ai_chars = sum(e.n_chars for e in ai)
    tools = [e for ld, e in ev if e.kind == "tool_call" and not e.is_subagent]
    short = sum(1 for _, e in users if len((e.text or "").strip()) <= SHORT_LEN)
    cont = sum(1 for _, e in users if (e.text or "").strip().lower().rstrip("。.!！~") in CONTINUE_WORDS)
    reliance = {
        "avg_user_chars": _ratio(user_chars, n_user),
        "avg_ai_chars": _ratio(ai_chars, len(ai)),
        "talk_ratio": _ratio(ai_chars, user_chars),
        "tool_share": _ratio(len(tools), len(tools) + len(ai)),
        "tools_per_msg": _ratio(len(tools), n_user),
        "short_rate": _ratio(short, n_user),
        "short_count": short,
        "continue_count": cont,
        "user_chars": user_chars,
        "ai_chars": ai_chars,
    }

    # ── 花费 ──
    by_model: Dict[Tuple[str, str], Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    sess_cost: Dict[Tuple[str, str], float] = defaultdict(float)
    plat_tok: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for ld, e in ev:
        if e.kind != "usage" or not e.tokens:
            continue
        key = (e.platform, e.model or "unknown")
        for k, v in e.tokens.items():
            by_model[key][k] += v
            plat_tok[e.platform][k] += v
        c, _, ok = pricing.cost(e.tokens, e.model)
        sess_cost[(e.platform, e.session_id)] += c
    models = []
    total_cost = 0.0
    priced_tokens = unpriced_tokens = approx_tokens = 0
    plat_cost: Dict[str, float] = defaultdict(float)
    for (plat, model), tk in sorted(by_model.items()):
        c, exact, ok = pricing.cost(tk, model)
        tsum = sum(tk.values())
        total_cost += c
        plat_cost[plat] += c
        if ok:
            priced_tokens += tsum
            if not exact:
                approx_tokens += tsum
        else:
            unpriced_tokens += tsum
        models.append({"platform": plat, "model": model, "tokens": dict(tk),
                       "total_tokens": tsum, "output": tk.get("output", 0),
                       "cost": round(c, 4), "priced": ok, "exact": exact})
    models.sort(key=lambda m: (-m["output"], m["model"]))
    all_tok = sum(m["total_tokens"] for m in models)
    plat_with_usage = sorted(plat_tok)
    spend = {
        "has_usage": bool(models),
        "total_tokens": all_tok,
        "output_tokens": sum(m["output"] for m in models),
        "cost": round(total_cost, 2),
        "approx": bool(approx_tokens or unpriced_tokens),
        "unpriced_share": _ratio(unpriced_tokens, all_tok),
        "models": models,
        "top_model": models[0]["model"] if models else None,
        "per_platform": {p: {"tokens": dict(plat_tok[p]), "cost": round(plat_cost[p], 2)}
                         for p in plat_with_usage},
        "platforms_without_usage": [p for p in platforms if p not in plat_tok],
    }

    # ── 会话（活跃段） ──
    sess_events: Dict[Tuple[str, str], List] = defaultdict(list)
    for ld, e in ev:
        if e.is_subagent or e.kind == "session_meta":
            continue
        sess_events[(e.platform, e.session_id)].append((ld, e))
    seg_best: Optional[dict] = None
    total_active = timedelta(0)
    sess_info: Dict[Tuple[str, str], dict] = {}
    for key, lst in sess_events.items():
        lst.sort(key=lambda x: x[0])
        seg_start = prev = lst[0][0]
        sess_active = timedelta(0)
        longest = timedelta(0)
        longest_start = seg_start
        for ld, _ in lst[1:] + [(None, None)]:
            if ld is None or ld - prev > GAP:
                dur = prev - seg_start
                sess_active += dur
                if dur > longest:
                    longest, longest_start = dur, seg_start
                if ld is not None:
                    seg_start = ld
            if ld is not None:
                prev = ld
        total_active += sess_active
        proj = next((e.project for _, e in lst if e.project), None)
        sess_info[key] = {"start": lst[0][0], "active": sess_active, "project": proj}
        if seg_best is None or (longest, key) > (seg_best["dur"], seg_best["key"]):
            seg_best = {"dur": longest, "start": longest_start, "key": key, "project": proj}

    # 项目匿名化映射（按用户消息数排序，保证稳定）
    proj_users = Counter(e.project for _, e in users if e.project)
    proj_order = [p for p, _ in sorted(proj_users.items(), key=lambda kv: (-kv[1], kv[0]))]
    pmap = redact.anonymize_projects(proj_order) if hide_projects else {}

    def pname(p: Optional[str]) -> Optional[str]:
        if p is None:
            return None
        return pmap.get(p, "项目 ?") if hide_projects else p

    top_sess = None
    if sess_cost:
        key, c = sorted(sess_cost.items(), key=lambda kv: (-kv[1], kv[0]))[0]
        info = sess_info.get(key, {})
        top_sess = {
            "cost": round(c, 2), "platform": key[0],
            "date": info["start"].date().isoformat() if info else None,
            "project": pname(info.get("project")) if info else None,
            "duration": _fmt_dur(info["active"]) if info else None,
        }

    file_counts: Counter = Counter()
    for _, e in ev:
        if e.kind == "tool_call" and e.tool_category == "edit":
            for f in e.files:
                file_counts[redact.file_label(f, hide_files)] += 1
    top_files = [{"name": n, "count": c}
                 for n, c in sorted(file_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:5]]
    tool_counts = Counter(e.tool_category for e in tools if e.tool_category in TOOL_LABEL)
    top_tools = [{"category": k, "label": TOOL_LABEL[k], "count": c}
                 for k, c in sorted(tool_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:3]]
    tinker = {
        "sessions": len(sess_events),
        "total_active": _fmt_dur(total_active),
        "total_active_hours": round(total_active.total_seconds() / 3600, 1),
        "longest_session": ({"duration": _fmt_dur(seg_best["dur"]),
                             "hours": round(seg_best["dur"].total_seconds() / 3600, 1),
                             "date": seg_best["start"].date().isoformat(),
                             "project": pname(seg_best["project"])} if seg_best else None),
        "top_project": ({"name": pname(proj_order[0]), "messages": proj_users[proj_order[0]]}
                        if proj_order else None),
        "projects": len(proj_order),
        "top_files": top_files,
        "top_tools": top_tools,
        "most_expensive_session": top_sess,
        "edit_count": sum(file_counts.values()),
    }

    # ── 双平台 ──
    cmp_ = None
    per_plat_users = Counter(e.platform for _, e in users)
    if len(per_plat_users) >= 2:
        shares = {p: _ratio(n, n_user) for p, n in sorted(per_plat_users.items())}
        rates = {}
        for p in shares:
            ps = [s for s in scored if s[2].platform == p]
            rates[p] = _ratio(sum(1 for s in ps if s[0] > 0), len(ps))
        tc = sum(plat_cost.values())
        main = max(shares, key=lambda k: (shares[k], k))
        angrier = max(rates, key=lambda k: (rates[k], k))
        cmp_ = {
            "message_share": shares,
            "cost_share": {p: _ratio(plat_cost.get(p, 0.0), tc) for p in shares},
            "angry_rate": rates,
            "main": main,
            "main_share": shares[main],
            "mode": "专一" if shares[main] >= 0.7 else "双修",
            "angrier": angrier,
        }

    m = {
        "window": {"since": since.isoformat() if since else None,
                   "until": until.isoformat() if until else None},
        "platforms": platforms,
        "user_msgs": n_user,
        "user_msgs_by_platform": dict(sorted(per_plat_users.items())),
        "events": len(ev),
        "rhythm": rhythm,
        "temper": temper,
        "reliance": reliance,
        "spend": spend,
        "tinker": tinker,
        "compare": cmp_,
    }
    return m
