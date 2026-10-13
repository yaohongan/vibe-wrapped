"""metrics.json + persona.json → poster.html → PNG。

截图三级降级：本机 Chrome/Chromium/Edge headless → Playwright → 只输出 HTML。
"""
from __future__ import annotations

import base64
import glob
import html
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from dataclasses import dataclass, field
from typing import List, Optional

import persona as persona_mod
import redact

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL = os.path.join(ROOT, "templates")
PLAT = persona_mod.PLAT_NAME
SIZES = {"1080x1440": (1080, 1440, "3x4"), "1080x1920": (1080, 1920, "9x16")}
NIGHT_HOURS = range(0, 5)


@dataclass
class Options:
    quotes: str = "redact"          # redact | show | none
    nickname: Optional[str] = None
    avatar: Optional[str] = None      # 头像图片路径
    repo_url: str = "github.com/yaohongan/vibe-wrapped"
    hide_projects: bool = False
    sizes: List[str] = field(default_factory=lambda: ["1080x1440", "1080x1920"])
    html_only: bool = False


# ───────────── 渲染器探测 ─────────────
def find_chrome() -> Optional[str]:
    env = os.environ.get("CHROME_PATH")
    cands = [env] if env else []
    cands += [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in cands:
        if c and os.path.exists(c):
            return c
    for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
              "microsoft-edge", "chrome"):
        p = shutil.which(n)
        if p:
            return p
    return None


def _has_playwright() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except Exception:
        return False


def available_renderers() -> List[str]:
    out = []
    if find_chrome():
        out.append("chrome-headless")
    if _has_playwright():
        out.append("playwright")
    return out


# ───────────── 字体 ─────────────
def font_face_css() -> str:
    """把 templates/fonts/ 里的字体内嵌进 HTML（base64），海报 HTML 可独立打开。"""
    css = []
    for path in sorted(glob.glob(os.path.join(TPL, "fonts", "*"))):
        base = os.path.basename(path)
        ext = os.path.splitext(base)[1].lower()
        fmt = {".woff2": "woff2", ".woff": "woff", ".ttf": "truetype", ".otf": "opentype"}.get(ext)
        if not fmt:
            continue
        family = ("JetBrains Mono" if "jetbrains" in base.lower() else "Smiley Sans")
        weight = "700 800" if family == "JetBrains Mono" else "400 900"
        with open(path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        mime = {"woff2": "font/woff2", "woff": "font/woff", "truetype": "font/ttf",
                "opentype": "font/otf"}[fmt]
        css.append(
            f"@font-face{{font-family:'{family}';src:url(data:{mime};base64,{b64}) "
            f"format('{fmt}');font-weight:{weight};font-display:block}}")
    return "\n".join(css)


# ───────────── 内容 ─────────────
def e(x) -> str:
    return html.escape(str(x), quote=True)


def _pct(x: float) -> str:
    return f"{x * 100:.0f}"


def avatar_html(o: Options) -> str:
    """头像：有图用图（base64 内嵌），没图但有昵称就用首字母占位圆。"""
    if o.avatar and os.path.isfile(o.avatar):
        ext = os.path.splitext(o.avatar)[1].lower().lstrip(".")
        mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "gif": "gif"}.get(ext)
        if mime:
            with open(o.avatar, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode()
            return f'<img class="avatar" alt="" src="data:image/{mime};base64,{b64}">'
    if o.nickname:
        return f'<span class="avatar ph">{e(o.nickname.strip()[:1].upper())}</span>'
    return ""


def heatmap_html(r: dict, window: dict) -> str:
    """年度打卡热力图：每格一天，周一在上，按周从左到右。"""
    daily = r.get("daily") or {}
    since = window.get("since") or r.get("first_day")
    until = window.get("until") or r.get("last_day")
    if not since or not until:
        return ""
    sd, real_end = date.fromisoformat(since), date.fromisoformat(until)
    end = date(sd.year, 12, 31) if sd.year == real_end.year else real_end
    if (end - sd).days > 371:
        sd = end - timedelta(days=370)
    span_days = (real_end - sd).days + 1
    if span_days <= 31:
        days = [sd + timedelta(days=i) for i in range(span_days)]
        mx = max([daily.get(d.isoformat(), 0) for d in days] + [1])
        names = "一二三四五六日"
        bars = []
        for d in days:
            v = daily.get(d.isoformat(), 0)
            wk = " we" if d.weekday() >= 5 else ""
            lab = names[d.weekday()] if span_days <= 7 else (str(d.day) if d.day in (1, 10, 20) or d == days[0] or d == days[-1] else "")
            bars.append(f'<div class="db{wk}"><i style="height:{(8 + v / mx * 92) if v else 3:.0f}%" '
                        f'class="{"on" if v else "off"}"></i><span>{lab}</span></div>')
        return f'<div class="daybars" style="--n:{len(days)}">{"".join(bars)}</div>'
    start = sd - timedelta(days=sd.weekday())
    vals = sorted(daily.values())
    n = len(vals)
    th = [vals[(n - 1) * k // 4] for k in (1, 2, 3)] if vals else [0, 0, 0]
    flat = bool(vals) and vals[0] == vals[-1]

    def level(v: int) -> int:
        if v <= 0:
            return 0
        if flat:
            return 4
        return 1 if v <= th[0] else 2 if v <= th[1] else 3 if v <= th[2] else 4

    cells, d = [], start
    while d <= end:
        if d < sd:
            cls = "x"
        elif d > real_end:
            cls = "f"
        else:
            cls = f"l{level(daily.get(d.isoformat(), 0))}"
        cells.append(f'<i class="{cls}"></i>')
        d += timedelta(days=1)
    weeks = (len(cells) + 6) // 7
    return f'<div class="heat" style="--weeks:{weeks}">{"".join(cells)}</div>'


def build_body(m: dict, p: dict, o: Options, tall: bool) -> str:
    r, t, d, s, tk = m["rhythm"], m["temper"], m["reliance"], m["spend"], m["tinker"]
    cmp_ = m.get("compare")
    label = p.get("label") or m["window"].get("label") or ""
    plats = [PLAT.get(x, x) for x in m["platforms"]]

    # 头部：头像 + 昵称（传播位）+ 平台
    chips = "".join(f'<span class="chip">{e(x)}</span>' for x in plats)
    ident = avatar_html(o)
    eyebrow = f'VIBE CHECK · {e(label)}'
    if ident:
        left = (f'<div class="row id">{ident}<div class="idtext">'
                f'<div class="nick">@{e(o.nickname)}</div>' if o.nickname else
                f'<div class="row id">{ident}<div class="idtext">')
        left += f'<div class="eyebrow">{eyebrow}</div></div></div>'
    else:
        left = f'<div><div class="eyebrow">{eyebrow}</div></div>'
    head = f'<div class="row head">{left}<div class="chips">{chips}</div></div>'

    # 人格卡
    ax = p["axes"]
    fl = p["axis_flags"]

    def axis(name, val, tag, thr):
        return (f'<div class="axis"><span class="name">{name}</span>'
                f'<div class="bar"><i style="width:{min(val, 100):.0f}%"></i><b style="left:{thr}%"></b></div>'
                f'<span class="val">{val:.0f}<small>{tag}</small></span></div>')

    axes_html = (axis("夜猫值", ax["N"], "夜" if fl["night"] else "昼", persona_mod.N_HIGH)
                 + axis("脾气值", ax["G"], "爆" if fl["angry"] else "温", persona_mod.G_HIGH)
                 + axis("放手值", ax["L"], "放" if fl["hands_off"] else "控", persona_mod.L_HIGH))
    note = f'<div class="warn">{e(p["sample_note"])}</div>' if p.get("sample_note") else ""
    code = "".join(f"<span>{e(c)}</span>" for c in p.get("code", ""))
    persona_html = (f'<div class="persona"><div class="glyph">{e(p.get("glyph", ""))}</div>'
                    f'<div class="stamp"><span>已打卡</span><b>{r["active_days"]}</b><span>天</span></div>'
                    f'<div class="kicker"><span class="code">{code}</span>你的 AI 编程人格是</div>'
                    f'<h1 data-fit>{e(p["name"])}</h1>'
                    f'<div class="tag">{e(p["tagline"])}</div>'
                    f'<div class="axes">{axes_html}</div>{note}</div>')

    # 作息 + 年度打卡
    lt = r.get("latest")
    bd = r.get("busiest_day")
    bd_txt = ""
    if bd:
        dd = date.fromisoformat(bd["date"])
        bd_txt = f' · 最肝 <b>{dd.month}/{dd.day}</b> 一天 <b>{bd["count"]}</b> 句'
    since = m["window"].get("since") or r.get("first_day")
    until = m["window"].get("until") or r.get("last_day")
    span = ((date.fromisoformat(until) - date.fromisoformat(since)).days + 1) if since and until else 0
    rhythm_html = (
        '<div class="panel"><h3 class="h3row"><span>打卡 · 最晚一次还在发指令</span><span class="legend">每格一天　少 <i class="l1"></i><i class="l2"></i><i class="l3"></i><i class="l4"></i> 多</span></h3><div class="rhythm">'
        f'<div><div class="big">{e(lt["time"]) if lt else "--:--"}</div></div>'
        f'<div><div class="sub">凌晨 0–5 点占 <b>{_pct(r["night_ratio"])}%</b> · 周末占 <b>{_pct(r["weekend_ratio"])}%</b><br>'
        f'打卡 <b>{r["active_days"]}</b>{f" / {span}" if span else ""} 天 · 最长连续 <b>{r["longest_streak"]}</b> 天{bd_txt}'
        '</div></div></div>'
        + heatmap_html(r, m["window"]) + '</div>')

    # 脾气
    q = t.get("quote")
    quote_html = ""
    if q and o.quotes != "none":
        txt = q["raw"] if o.quotes == "show" else redact.redact_text(q["raw"])
        quote_html = (f'<div class="quote" data-fit-box>{e(redact.truncate(txt, 30))}'
                      f'<cite>—— 我对 {e(PLAT.get(q["platform"], q["platform"]))} 说过最凶的一句</cite></div>')
    temper_html = (
        '<div class="panel temper"><h3>脾气 · 暴躁命中率</h3>'
        f'<div class="big">{_pct(t["angry_rate"])}<small>%</small></div>'
        f'<div class="kv" style="margin-top:10px"><span>骂过 <b>{t["angry_count"]}</b> 次 · 打断 AI <b>{t["interrupts"]}</b> 次</span>'
        f'<span>说了 <b>{t["polite_count"]}</b> 次谢谢 / 请</span></div>{quote_html}</div>')

    # 花费 & 折腾
    if s["has_usage"]:
        approx = "约 " if s["approx"] else ""
        cost = f'{approx}{persona_mod.fmt_money(s["cost"])}'
        cost_cell = (f'<div class="stat"><div class="big">{e(cost)}</div>'
                     f'<div class="lbl tea">🧋 折合约 {persona_mod.tea_cups(s["cost"]):,} 杯奶茶</div>'
                     f'<div class="lbl">{e(persona_mod.fmt_tokens(s["total_tokens"]))} token · API 价估算，订阅不同</div></div>')
        miss = ""
        if s["platforms_without_usage"]:
            names = "、".join(PLAT.get(x, x) for x in s["platforms_without_usage"])
            miss = f'<div class="warn">{e(names)} 日志无 token 数据，未计入</div>'
    else:
        cost_cell = '<div class="stat"><div class="big">—</div><div class="lbl">日志里没有 token 数据<br>不估算、不编</div></div>'
        miss = ""
    ls = tk.get("longest_session")
    es = tk.get("most_expensive_session")
    kv = []
    if ls:
        kv.append(f'最长连续 <b>{e(ls["duration"])}</b>')
    if es and s["has_usage"]:
        proj = f' · {e(es["project"])}' if es.get("project") else ""
        kv.append(f'最贵一场 <b>{e(persona_mod.fmt_money(es["cost"]))}</b>{proj}')
    if tk["top_files"]:
        kv.append(f'最常改 <b>{e(tk["top_files"][0]["name"])}</b> ×{tk["top_files"][0]["count"]}')
    kv.insert(0, f'<b>{tk["sessions"]}</b> 场会话 · <b>{tk["total_active_hours"]:.0f}</b> 小时')
    spend_html = (
        '<div class="panel tight"><h3>花费</h3>' + cost_cell + miss + '</div>')
    tinker_html = (
        '<div class="panel tight"><h3>折腾</h3><div class="kv">'
        + "".join(f"<span>{x}</span>" for x in kv[:3]) + '</div></div>')
    mid_html = (f'<div class="grid2 mid">{temper_html}'
                f'<div class="col">{spend_html}{tinker_html}</div></div>')

    # 双平台 / Top3 工具
    if cmp_:
        ids = list(cmp_["message_share"])
        a, b = ids[0], ids[1]
        sa, sb = cmp_["message_share"][a], cmp_["message_share"][b]
        ra, rb = cmp_["angry_rate"][a], cmp_["angry_rate"][b]
        cmp_html = (
            f'<div class="panel"><h3 class="h3row"><span>双平台 · {e(cmp_["mode"])}</span></h3>'
            f'<div class="share"><i class="a" style="width:{sa * 100:.1f}%"></i><i class="b" style="width:{sb * 100:.1f}%"></i></div>'
            f'<div class="cmp-line">{e(PLAT.get(a, a))} <b>{_pct(sa)}%</b> · {e(PLAT.get(b, b))} <b>{_pct(sb)}%</b>　'
            f'挨骂 <b>{_pct(ra)}%</b> vs <b>{_pct(rb)}%</b>，更凶的是 <b>{e(PLAT.get(cmp_["angrier"], cmp_["angrier"]))}</b></div></div>')
    else:
        tools = "　".join(f'{e(x["label"])} <b>{x["count"]:,}</b>' for x in tk["top_tools"]) or "—"
        cmp_html = (f'<div class="panel"><h3>AI 最常替你干的活</h3>'
                    f'<div class="cmp-line">{tools}</div></div>')

    # 徽章 + 诊断 + 短评
    badges = "".join(f'<span class="badge">{e(b["icon"])} {e(b["title"])}</span>' for b in p["badges"][:3])
    badges_html = f'<div class="badges">{badges}</div>' if badges else ""
    roast = p.get("roast") or p["roast_fallback"]
    diag = p["diagnosis"]
    final_html = (
        '<div class="panel"><h3>你和 AI 的关系</h3>'
        f'<div class="diag"><span class="t">{e(diag["name"])}</span><span class="d">{e(diag["desc"])}</span></div>'
        f'<div class="roast" data-fit-box>{e(roast)}</div></div>')

    foot = (f'<div class="foot"><div class="cta"><div class="q">你是哪一型？本地生成·数据不上传，评论区交代号 👇</div>'
            f'<div class="repo">{e(o.repo_url)}</div></div>'
            f'<div class="note">对 Claude Code / Codex 说<br>“生成我的 vibe 本周报告”</div></div>')

    parts = [head, persona_html, rhythm_html, mid_html, cmp_html, badges_html, final_html]
    parts.append(foot)
    return "\n".join(x for x in parts if x)


def build_html(m: dict, p: dict, o: Options, size: str) -> str:
    w, h, _ = SIZES[size]
    with open(os.path.join(TPL, "poster.html"), encoding="utf-8") as fh:
        tpl = fh.read()
    with open(os.path.join(TPL, "poster.css"), encoding="utf-8") as fh:
        css = fh.read()
    rep = {
        "{{theme}}": "dark" if p["dark"] else "light",
        "{{shape}}": "tall" if h > 1500 else "std",
        "{{title}}": e(f'{p["name"]} · Vibe Check'),
        "{{fonts}}": font_face_css(),
        "{{css}}": css,
        "{{bg}}": e(p["bg"]), "{{bg2}}": e(p["bg2"]), "{{accent}}": e(p["accent"]), "{{height}}": str(h),
        "{{body}}": build_body(m, p, o, tall=h > 1500),
    }
    out = tpl
    for k, v in rep.items():
        out = out.replace(k, v)
    if not p["dark"]:
        out = out.replace('<html lang="zh-CN" class="light', '<html lang="zh-CN" class="light')
    return out


# ───────────── 截图 ─────────────
def shoot_chrome(chrome: str, html_path: str, png_path: str, w: int, h: int) -> bool:
    prof = tempfile.mkdtemp(prefix="vibe-wrapped-chrome-")
    try:
        cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
               "--force-device-scale-factor=2", f"--window-size={w},{h}",
               "--virtual-time-budget=4000", "--run-all-compositor-stages-before-draw",
               f"--user-data-dir={prof}", f"--screenshot={png_path}",
               "file://" + html_path]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
        return os.path.exists(png_path) and os.path.getsize(png_path) > 5000
    except Exception:
        return False
    finally:
        shutil.rmtree(prof, ignore_errors=True)


def shoot_playwright(html_path: str, png_path: str, w: int, h: int) -> bool:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            pg = br.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
            pg.goto("file://" + html_path)
            pg.wait_for_function("document.documentElement.dataset.ready==='1'", timeout=10000)
            pg.screenshot(path=png_path, clip={"x": 0, "y": 0, "width": w, "height": h})
            br.close()
        return os.path.exists(png_path)
    except Exception:
        return False


def render_all(m: dict, p: dict, out_dir: str, o: Options) -> List[str]:
    os.makedirs(out_dir, exist_ok=True)
    produced: List[str] = []
    chrome = None if o.html_only else find_chrome()
    pw_ok = (not o.html_only) and _has_playwright()
    for size in o.sizes:
        w, h, tag = SIZES[size]
        html_path = os.path.abspath(os.path.join(out_dir, f"poster-{tag}.html"))
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(build_html(m, p, o, size))
        produced.append(html_path)
        png = os.path.abspath(os.path.join(out_dir, f"poster-{tag}.png"))
        if os.path.exists(png):
            os.remove(png)
        ok = False
        if chrome:
            ok = shoot_chrome(chrome, html_path, png, w, h)
        if not ok and pw_ok:
            ok = shoot_playwright(html_path, png, w, h)
        if ok:
            produced.append(png)
        elif not o.html_only:
            print(f"⚠ 没能截图（未找到 Chrome/Playwright）。请用浏览器打开 {html_path} 自行截图。",
                  file=sys.stderr)
    return produced
