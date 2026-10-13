#!/usr/bin/env python3
"""vibe-wrapped 总入口：collect → metrics → persona → render。

子命令：doctor | scan | stats | roast | render | all | profile
全程本地，不联网。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import date, datetime, timedelta
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import metrics as metrics_mod   # noqa: E402
import persona as persona_mod   # noqa: E402
from adapters import ADAPTERS, detect  # noqa: E402

REPO_URL = "github.com/yaohongan/vibe-wrapped"
DEFAULT_OUT = "~/vibe-wrapped-out"
PROFILE_DIR = os.path.expanduser("~/.vibe-wrapped")
PROFILE_PATH = os.path.join(PROFILE_DIR, "profile.json")

# 时间维度：key → (天数 or None, 展示名)。None 表示特殊处理。
RANGES = {
    "week": (7, "近 7 天"),
    "month": (30, "近 30 天"),
    "quarter": (90, "近 90 天"),
    "halfyear": (180, "近半年"),
    "year": (None, "今年至今"),
    "all": (None, "全部时间"),
    "auto": (None, "自动"),
}
RANGE_ALIASES = {
    "本周": "week", "一周": "week", "周": "week", "7d": "week",
    "本月": "month", "一个月": "month", "月": "month", "30d": "month",
    "季度": "quarter", "三个月": "quarter", "近三个月": "quarter", "90d": "quarter",
    "半年": "halfyear", "近半年": "halfyear", "180d": "halfyear",
    "今年": "year", "一年": "year", "年": "year", "全年": "year",
    "全部": "all", "所有": "all", "至今": "all",
}


def _tz(name: Optional[str]):
    if not name:
        return None
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        sys.exit(f"无法识别时区：{name}（示例：Asia/Shanghai）")


def _resolve_range(value: Optional[str]) -> str:
    v = (value or "auto").strip().lower()
    v = RANGE_ALIASES.get(v, RANGE_ALIASES.get(value or "", v))
    if v not in RANGES:
        sys.exit(f"不认识的时间范围：{value}。可选：week / month / quarter / halfyear / year / all，"
                 "或用 --since/--until 指定日期。")
    return v


def _window(args, events=None, tz=None):
    """返回 (since, until, label, year)。优先级：--since/--until > --year > --range。"""
    today = datetime.now(tz).date() if tz else date.today()
    if args.since or args.until:
        since = date.fromisoformat(args.since) if args.since else None
        until = date.fromisoformat(args.until) if args.until else today
        label = f"{since.isoformat() if since else '最早'} ~ {until.isoformat()}"
        return since, until, label, None
    if args.year:
        y = args.year
        return date(y, 1, 1), (today if y == today.year else date(y, 12, 31)), f"{y} 年", y
    key = _resolve_range(args.range)
    if key == "all" or key == "auto":
        first = None
        if events:
            first = min((e.ts.astimezone(tz) if tz else e.ts.astimezone()).date() for e in events)
        if key == "auto" and first and (today - first).days + 1 >= RANGES["month"][0]:
            key = "month"
        else:
            n = ((today - first).days + 1) if first else 0
            label = f"全部时间（{n} 天）" if n else "全部时间"
            return None, None, label, None
    if key == "year":
        return date(today.year, 1, 1), today, f"{today.year} 年至今", today.year
    days, label = RANGES[key]
    return today - timedelta(days=days - 1), today, label, None


def _out_dir(args) -> str:
    d = os.path.expanduser(args.out or DEFAULT_OUT)
    os.makedirs(d, exist_ok=True)
    return d


def _dump(path: str, obj) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def _load(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _profile() -> dict:
    try:
        return _load(PROFILE_PATH)
    except (OSError, ValueError):
        return {}


# ───────────── doctor / scan ─────────────
def cmd_doctor(args) -> int:
    import render
    print(f"Python {sys.version.split()[0]}", "OK" if sys.version_info >= (3, 9) else "需要 ≥3.9")
    found = detect()
    if not found:
        print("未找到 Claude Code / Codex 会话日志（~/.claude/projects、~/.codex/sessions）")
    for p, n in found.items():
        print(f"日志：{p} — {n} 个文件")
    r = render.available_renderers()
    print("渲染器：", ", ".join(r) if r else "无（将只输出 HTML，用户自行截图）")
    prof = _profile()
    if prof:
        print("海报昵称：", prof.get("nickname") or "(无)")
    return 0 if found else 1


def cmd_scan(args) -> int:
    """各平台日志的起止日期与条数，用来判断哪些时间维度有意义。"""
    tz = _tz(args.tz)
    out = {}
    for name, mod in ADAPTERS.items():
        evs, st = mod.collect()
        users = [e for e in evs if e.kind == "user_msg" and not e.is_subagent]
        if not evs:
            continue
        days = sorted({(e.ts.astimezone(tz) if tz else e.ts.astimezone()).date() for e in evs})
        out[name] = {"files": st.files, "user_msgs": len(users),
                     "first": days[0].isoformat(), "last": days[-1].isoformat(),
                     "span_days": (days[-1] - days[0]).days + 1}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out else 1


# ───────────── stats ─────────────
def cmd_stats(args) -> int:
    tz = _tz(args.tz)
    events, all_stats = [], []
    only = [args.platform] if args.platform else list(ADAPTERS)
    for name in only:
        evs, st = ADAPTERS[name].collect()
        events.extend(evs)
        all_stats.append(st)
        if st.files:
            print(f"[{name}] {st.files} 个文件，{st.lines} 行，坏行 {st.bad_lines}")
            if st.lines and st.bad_ratio > 0.05:
                print(f"  ⚠ 日志格式可能更新了：坏行占比 {st.bad_ratio:.1%}")
    if not events:
        print("没有读到任何会话日志。先用 `wrapped.py doctor` 检查。")
        return 1
    since, until, label, year = _window(args, events, tz)
    m = metrics_mod.compute(events, tz=tz, since=since, until=until,
                            hide_projects=not args.show_projects)
    m["parse"] = [s.as_dict() for s in all_stats]
    m["window"]["label"] = label
    p = persona_mod.build(m, year=year, label=label)
    out = _out_dir(args)
    _dump(os.path.join(out, "metrics.json"), m)
    _dump(os.path.join(out, "persona.json"), p)
    _dump(os.path.join(out, "run.json"), {
        "hide_projects": not args.show_projects, "label": label, "year": year,
        "since": since.isoformat() if since else None,
        "until": until.isoformat() if until else None,
        "generated": datetime.now().strftime("%Y-%m-%d"),
    })
    print(f"时间范围：{label}")
    print(f"人格：{p['code']}｜{p['name']}  N={p['axes']['N']} G={p['axes']['G']} L={p['axes']['L']}")
    print(f"用户消息 {m['user_msgs']} 条；输出目录：{out}")
    if m["user_msgs"] == 0:
        print("  这个时间范围内没有用户消息，换个更长的范围试试（如 --range all）。")
    elif m["user_msgs"] < persona_mod.MIN_SAMPLE:
        print("  样本少（<50 条），人格标注为“见习”。")
    return 0


# ───────────── roast ─────────────
def cmd_roast(args) -> int:
    path = os.path.join(_out_dir(args), "persona.json")
    if not os.path.exists(path):
        sys.exit("先运行 stats。")
    text = " ".join((args.text or "").split())
    if not text:
        sys.exit("--text 不能为空")
    if len(text) > 40:
        text = text[:39] + "…"
    p = _load(path)
    p["roast"] = text
    _dump(path, p)
    print("已写入短评：", text)
    return 0


# ───────────── profile（昵称） ─────────────
def cmd_profile(args) -> int:
    if args.clear:
        shutil.rmtree(PROFILE_DIR, ignore_errors=True)
        print("已清除昵称。")
        return 0
    prof = _profile()
    prof.pop("avatar", None)          # 旧版本保存过的头像字段，不再使用
    if args.nickname is not None:
        prof["nickname"] = args.nickname.strip().lstrip("@")
    os.makedirs(PROFILE_DIR, exist_ok=True)
    for old in os.listdir(PROFILE_DIR):
        if old.startswith("avatar."):
            os.remove(os.path.join(PROFILE_DIR, old))
    _dump(PROFILE_PATH, prof)
    print("已保存昵称：", prof.get("nickname") or "(无)")
    print("只存在本机", PROFILE_DIR, "，下次出图自动使用。")
    return 0


# ───────────── render ─────────────
def cmd_render(args) -> int:
    import render
    out = _out_dir(args)
    try:
        m = _load(os.path.join(out, "metrics.json"))
        p = _load(os.path.join(out, "persona.json"))
    except OSError:
        sys.exit("找不到 metrics.json / persona.json，先运行 stats。")
    run = {}
    if os.path.exists(os.path.join(out, "run.json")):
        run = _load(os.path.join(out, "run.json"))
    prof = _profile()
    opts = render.Options(
        quotes="none" if args.no_quotes else ("show" if args.show_quotes else "redact"),
        nickname=args.nickname if args.nickname is not None else prof.get("nickname"),
        repo_url=REPO_URL,
        hide_projects=run.get("hide_projects", True),
        sizes=[args.size] if args.size else ["1080x1440", "1080x1920"],
        html_only=args.html_only,
    )
    files = render.render_all(m, p, out, opts)
    with open(os.path.join(out, "share.txt"), "w", encoding="utf-8") as fh:
        fh.write(persona_mod.share_text(m, p, REPO_URL, nickname=opts.nickname))
    for f in files + [os.path.join(out, "share.txt")]:
        print("生成：", f)
    return 0


def cmd_all(args) -> int:
    rc = cmd_stats(args)
    return rc or cmd_render(args)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="wrapped.py", description="Vibe Check：Vibe Coding 人格报告（本地生成）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(sp, window=False, render_opts=False):
        sp.add_argument("--out", default=DEFAULT_OUT, help="输出目录")
        if window:
            sp.add_argument("--range", default="auto",
                            help="时间范围：week | month | quarter | halfyear | year | all（也认 本周/本月/半年/今年/全部）；"
                                 "默认 auto = 近 30 天，数据不足 30 天则取全部")
            sp.add_argument("--year", type=int, help="指定某一整年")
            sp.add_argument("--since", help="起始日期 YYYY-MM-DD")
            sp.add_argument("--until", help="结束日期 YYYY-MM-DD")
            sp.add_argument("--all", dest="range", action="store_const", const="all", help="等同于 --range all")
            sp.add_argument("--tz", help="时区，如 Asia/Shanghai（默认系统时区）")
            sp.add_argument("--platform", choices=sorted(ADAPTERS), help="只统计一个平台")
            sp.add_argument("--show-projects", action="store_true",
                            help="海报显示真实项目名/文件名（默认匿名为 项目 A/B、*.tsx）")
        if render_opts:
            sp.add_argument("--size", choices=["1080x1440", "1080x1920"])
            sp.add_argument("--nickname", help="海报上显示的昵称（覆盖已保存的）")
            g = sp.add_mutually_exclusive_group()
            g.add_argument("--show-quotes", action="store_true", help="关闭原话脱敏")
            g.add_argument("--no-quotes", action="store_true", help="海报不显示原话")
            sp.add_argument("--html-only", action="store_true", help="只输出 HTML，不截图")

    s = sub.add_parser("doctor"); s.set_defaults(fn=cmd_doctor)
    s = sub.add_parser("scan"); s.add_argument("--tz"); s.set_defaults(fn=cmd_scan)
    s = sub.add_parser("stats"); common(s, window=True); s.set_defaults(fn=cmd_stats)
    s = sub.add_parser("roast"); s.add_argument("--out", default=DEFAULT_OUT)
    s.add_argument("--text", required=True); s.set_defaults(fn=cmd_roast)
    s = sub.add_parser("render"); common(s, render_opts=True); s.set_defaults(fn=cmd_render)
    s = sub.add_parser("all"); common(s, window=True, render_opts=True); s.set_defaults(fn=cmd_all)
    s = sub.add_parser("profile", help="保存海报上的昵称（只存本机）")
    s.add_argument("--nickname"); s.add_argument("--clear", action="store_true")
    s.set_defaults(fn=cmd_profile)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
