#!/usr/bin/env python3
"""vibe-wrapped 总入口：collect → metrics → persona → render。

子命令：doctor | stats | roast | render | all
全程本地，不联网。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import metrics as metrics_mod   # noqa: E402
import persona as persona_mod   # noqa: E402
from adapters import ADAPTERS, detect  # noqa: E402

REPO_URL = "github.com/yaohongan/vibe-wrapped"
DEFAULT_OUT = "~/vibe-wrapped-out"


def _tz(name: Optional[str]):
    if not name:
        return None
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        sys.exit(f"无法识别时区：{name}（示例：Asia/Shanghai）")


def _window(args):
    today = date.today()
    if args.all:
        return None, None, None
    year = args.year or today.year
    since = date.fromisoformat(args.since) if args.since else date(year, 1, 1)
    until = date.fromisoformat(args.until) if args.until else (
        today if year == today.year else date(year, 12, 31))
    return since, until, year


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


# ───────────── doctor ─────────────
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
    return 0 if found else 1


# ───────────── stats ─────────────
def cmd_stats(args) -> int:
    since, until, year = _window(args)
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
    m = metrics_mod.compute(events, tz=tz, since=since, until=until,
                            hide_projects=not args.show_projects)
    m["parse"] = [s.as_dict() for s in all_stats]
    p = persona_mod.build(m, year=year)
    out = _out_dir(args)
    _dump(os.path.join(out, "metrics.json"), m)
    _dump(os.path.join(out, "persona.json"), p)
    _dump(os.path.join(out, "run.json"), {
        "hide_projects": not args.show_projects, "year": year,
        "since": since.isoformat() if since else None,
        "until": until.isoformat() if until else None,
        "generated": datetime.now().strftime("%Y-%m-%d"),
    })
    print(f"人格：{p['name']}  N={p['axes']['N']} G={p['axes']['G']} L={p['axes']['L']}")
    print(f"用户消息 {m['user_msgs']} 条；输出目录：{out}")
    if m["user_msgs"] < persona_mod.MIN_SAMPLE:
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
    opts = render.Options(
        quotes="none" if args.no_quotes else ("show" if args.show_quotes else "redact"),
        nickname=args.nickname, repo_url=REPO_URL,
        hide_projects=run.get("hide_projects", True),
        sizes=[args.size] if args.size else ["1080x1440", "1080x1920"],
        html_only=args.html_only,
    )
    files = render.render_all(m, p, out, opts)
    with open(os.path.join(out, "share.txt"), "w", encoding="utf-8") as fh:
        fh.write(persona_mod.share_text(m, p, REPO_URL))
    for f in files + [os.path.join(out, "share.txt")]:
        print("生成：", f)
    return 0


def cmd_all(args) -> int:
    rc = cmd_stats(args)
    return rc or cmd_render(args)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="wrapped.py", description="Vibe Coding 人格年报（本地生成）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(sp, window=False, render_opts=False):
        sp.add_argument("--out", default=DEFAULT_OUT, help="输出目录")
        if window:
            sp.add_argument("--year", type=int)
            sp.add_argument("--since", help="YYYY-MM-DD")
            sp.add_argument("--until", help="YYYY-MM-DD")
            sp.add_argument("--all", action="store_true", help="统计全部历史")
            sp.add_argument("--tz", help="时区，如 Asia/Shanghai（默认系统时区）")
            sp.add_argument("--platform", choices=sorted(ADAPTERS), help="只统计一个平台")
            sp.add_argument("--show-projects", action="store_true",
                            help="海报显示真实项目名/文件名（默认匿名为 项目 A/B、*.tsx）")
        if render_opts:
            sp.add_argument("--size", choices=["1080x1440", "1080x1920"])
            sp.add_argument("--nickname", help="海报上显示的昵称")
            g = sp.add_mutually_exclusive_group()
            g.add_argument("--show-quotes", action="store_true", help="关闭原话脱敏")
            g.add_argument("--no-quotes", action="store_true", help="海报不显示原话")
            sp.add_argument("--html-only", action="store_true", help="只输出 HTML，不截图")

    s = sub.add_parser("doctor"); s.set_defaults(fn=cmd_doctor)
    s = sub.add_parser("stats"); common(s, window=True); s.set_defaults(fn=cmd_stats)
    s = sub.add_parser("roast"); s.add_argument("--out", default=DEFAULT_OUT)
    s.add_argument("--text", required=True); s.set_defaults(fn=cmd_roast)
    s = sub.add_parser("render"); common(s, render_opts=True); s.set_defaults(fn=cmd_render)
    s = sub.add_parser("all"); common(s, window=True, render_opts=True); s.set_defaults(fn=cmd_all)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
