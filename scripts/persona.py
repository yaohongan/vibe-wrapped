"""metrics → 三轴分数 → 8 种人格 + 关系诊断 + 成就徽章 + 分享文案。

判定完全确定，AI 不参与。阈值是初版值，集中放在下面常量里，方便校准。
"""
from __future__ import annotations

from typing import Dict, List, Optional

# ───── 可校准常量 ─────
N_NIGHT_W = 2.0        # 凌晨占比权重
N_WEEKEND_W = 0.5      # 周末占比权重
G_ANGRY_W = 4.0        # 暴躁命中率权重
N_HIGH, G_HIGH, L_HIGH = 30, 25, 55
MIN_SAMPLE = 50        # 用户消息数低于此值 → “（见习）”

PERSONAS = {
    # (夜?, 爆?, 放?) → 人格
    (True, True, True): {
        "id": "night-angry-hands-off", "name": "深夜甩锅型",
        "tagline": "半夜三点丢一句“修好它”，修不好就骂",
        "bg": "#170B33", "bg2": "#4A0F3D", "accent": "#FF3D7F", "glyph": "🌙", "dark": True,
        "roasts": ["你不是在写代码，你是在凌晨给 AI 派活然后骂它。",
                   "{latest}还在发指令，AI 没睡，你的黑眼圈替它加班。",
                   "{angry}% 的消息在骂人，剩下的在说“继续”。"]},
    (True, True, False): {
        "id": "night-angry-control", "name": "熬夜暴躁监工",
        "tagline": "一行行盯着改，越晚越凶",
        "bg": "#0B0B0B", "bg2": "#3A1204", "accent": "#FF5A1F", "glyph": "🔦", "dark": True,
        "roasts": ["凌晨 4 点的“不对”，AI 记住了，你女朋友也记住了。",
                   "{night}% 的消息在凌晨发出，你是 AI 唯一的夜班领导。",
                   "盯得这么紧，{angry}% 的暴躁率，AI 比你的甲方还难。"]},
    (True, False, True): {
        "id": "night-calm-hands-off", "name": "午夜甩手掌柜",
        "tagline": "睡前说一句“继续”，第二天看结果",
        "bg": "#0E1740", "bg2": "#1B3A8A", "accent": "#8FB4FF", "glyph": "😴", "dark": True,
        "roasts": ["你的作息只有 AI 知道，它也不敢说。",
                   "短指令占 {short}%：你对 AI 说得最多的是“继续”。",
                   "凌晨发一句“继续”，早上收货，AI 才是夜班工人。"]},
    (True, False, False): {
        "id": "night-calm-control", "name": "深夜温柔调教型",
        "tagline": "凌晨还在耐心解释第五遍",
        "bg": "#1B1638", "bg2": "#3B2A66", "accent": "#C9A7FF", "glyph": "🕯️", "dark": True,
        "roasts": ["这么好的耐心，建议分一点给现实里的人。",
                   "骂人率只有 {angry}%，你是凌晨最温柔的 AI 家长。",
                   "{night}% 的话在深夜说完，AI 比你的朋友更懂你的作息。"]},
    (False, True, True): {
        "id": "day-angry-hands-off", "name": "白天甩锅型",
        "tagline": "上班时间外包给 AI，出事全怪它",
        "bg": "#FFE8CC", "bg2": "#FFC078", "accent": "#D9480F", "glyph": "💥", "dark": False,
        "roasts": ["需求一句话，骂人一段话。",
                   "{angry}% 的消息带火药味，短指令还占 {short}%，典型“你看着办但你办错了”。",
                   "活让 AI 干，气自己生，这是什么新型劳动关系。"]},
    (False, True, False): {
        "id": "day-angry-control", "name": "暴躁监工型",
        "tagline": "朝九晚六，盯得死死的，错一个字都不行",
        "bg": "#FFE0E0", "bg2": "#FFA8A8", "accent": "#C2255C", "glyph": "👀", "dark": False,
        "roasts": ["你不需要 AI，你需要一个能骂的实习生。",
                   "{angry}% 的暴躁率，且作息正常，纯粹是脾气不好。",
                   "朝九晚六骂得有条不紊，AI 都想申请工伤。"]},
    (False, False, True): {
        "id": "day-calm-hands-off", "name": "甩手掌柜型",
        "tagline": "“你看着办”，然后真让它看着办",
        "bg": "#DFF5E3", "bg2": "#A9E3B8", "accent": "#2B8A3E", "glyph": "🍵", "dark": False,
        "roasts": ["代码是 AI 写的，PR 是你提的，锅是谁的心里有数。",
                   "短指令占 {short}%，你的主要贡献是说“继续”。",
                   "AI 干了 {msgs} 轮活，你负责点头，职场天赋拉满。"]},
    (False, False, False): {
        "id": "day-calm-control", "name": "温柔调教型",
        "tagline": "正常作息、说话客气、事事过问",
        "bg": "#EBE4FF", "bg2": "#CDBDFF", "accent": "#5F3DC4", "glyph": "🌱", "dark": False,
        "roasts": ["你是 AI 最想要的用户，也是最无聊的那种。",
                   "{angry}% 的暴躁率，你是怎么做到和 AI 不吵架的？",
                   "作息健康、脾气稳定、事事过问，建议去带新人。"]},
}

DIAGNOSES = [
    ("相爱相杀", "骂了一整年，一天都没离开"),
    ("脚踏两条船", "Claude 和 Codex 都以为自己是唯一"),
    ("冷暴力", "你对它说得最多的是“继续”"),
    ("深夜限定", "白天不联系，晚上才想起它"),
    ("单方面倾诉", "你说得比它还多"),
    ("稳定搭子", "不吵不闹，按时上班"),
]


def axes(m: dict) -> Dict[str, float]:
    r, t, d = m["rhythm"], m["temper"], m["reliance"]
    n = min(100.0, r["night_ratio"] * 100 * N_NIGHT_W + r["weekend_ratio"] * 100 * N_WEEKEND_W)
    g = min(100.0, t["angry_rate"] * 100 * G_ANGRY_W)
    l = (d["short_rate"] * 50
         + min(d["talk_ratio"] / 20, 1) * 30
         + min(d["tools_per_msg"] / 10, 1) * 20)
    return {"N": round(n, 1), "G": round(g, 1), "L": round(l, 1)}


def diagnose(m: dict) -> dict:
    r, t, d, c = m["rhythm"], m["temper"], m["reliance"], m.get("compare")
    both_mid = bool(c) and all(0.3 <= s <= 0.7 for s in c["message_share"].values())
    conds = [
        t["angry_rate"] >= 0.20 and r["longest_streak"] >= 30,
        both_mid,
        d["short_rate"] >= 0.50,
        r["night_ratio"] >= 0.25,
        d["avg_user_chars"] >= 200,
        True,
    ]
    for (name, desc), ok in zip(DIAGNOSES, conds):
        if ok:
            return {"name": name, "desc": desc}
    return {"name": DIAGNOSES[-1][0], "desc": DIAGNOSES[-1][1]}


def badges(m: dict) -> List[dict]:
    r, t, d, s, c = m["rhythm"], m["temper"], m["reliance"], m["spend"], m.get("compare")
    out = []   # (优先级, 徽章)

    def add(prio, icon, title, desc):
        out.append((prio, {"icon": icon, "title": title, "desc": desc}))

    lt = r.get("latest")
    if lt and lt["is_after_midnight"]:
        if 3 <= lt["hour"] < 5:
            add(1, "🌙", "凌晨四点之王", f"最晚一次 {lt['time']} 还在发指令")
        elif lt["hour"] >= 5:
            add(1, "🌅", "通宵到天亮", f"最晚一次 {lt['time']}，窗外已经亮了")
        else:
            add(1, "🦉", "午夜场选手", f"最晚一次 {lt['time']} 还在发指令")
    if t["angry_rate"] >= 0.20:
        add(2, "🔥", "暴躁老哥", f"{t['angry_rate'] * 100:.0f}% 的消息带火药味")
    if d["continue_count"] >= 20:
        add(3, "🙏", "“继续”教徒", f"说了 {d['continue_count']} 次继续 / ok / 好")
    if t["interrupts"] >= 30:
        add(4, "✋", "打断狂魔", f"主动打断 AI {t['interrupts']} 次")
    if s["has_usage"] and s["cost"] >= 500:
        add(5, "💸", "token 焚化炉", f"按 API 价约 ${s['cost']:,.0f}")
    if r["longest_streak"] >= 30:
        add(6, "📆", "全勤打工人", f"连续 {r['longest_streak']} 天没离开过 AI")
    if c and c["mode"] == "双修":
        add(7, "⚔️", "双修玩家", "Claude 和 Codex 轮流上岗")
    if r["weekend_ratio"] >= 0.40:
        add(8, "🛠", "周末战士", f"{r['weekend_ratio'] * 100:.0f}% 的指令发在周末")
    if t["polite_count"] >= 15 and t["angry_rate"] < 0.05:
        add(9, "🎩", "礼貌天花板", f"对 AI 说了 {t['polite_count']} 次谢谢/请")
    if d["avg_user_chars"] >= 200:
        add(10, "📜", "小作文选手", f"平均每条 {d['avg_user_chars']:.0f} 字")
    if 0 < d["avg_user_chars"] <= 12:
        add(11, "🤏", "惜字如金", f"平均每条只有 {d['avg_user_chars']:.0f} 字")
    out.sort(key=lambda x: x[0])
    return [b for _, b in out][:4]


def fmt_tokens(n: float) -> str:
    if n >= 1e8:
        return f"{n / 1e8:.1f} 亿"
    if n >= 1e4:
        return f"{n / 1e4:.0f} 万"
    return f"{int(n)}"


USD_CNY = 7.1          # 仅用于“折合奶茶”的趣味换算
TEA_CNY = 15           # 一杯奶茶


def tea_cups(cost_usd: float) -> int:
    return int(round(cost_usd * USD_CNY / TEA_CNY))


def fmt_money(x: float) -> str:
    return f"${x:,.0f}" if x >= 100 else f"${x:,.2f}"


def build(m: dict, year: Optional[int] = None) -> dict:
    ax = axes(m)
    key = (ax["N"] >= N_HIGH, ax["G"] >= G_HIGH, ax["L"] >= L_HIGH)
    p = PERSONAS[key]
    n_user = m["user_msgs"]
    rookie = n_user < MIN_SAMPLE
    r, t, d = m["rhythm"], m["temper"], m["reliance"]
    lt = r.get("latest")
    fmt = {
        "night": f"{r['night_ratio'] * 100:.0f}", "angry": f"{t['angry_rate'] * 100:.0f}",
        "short": f"{d['short_rate'] * 100:.0f}", "msgs": f"{n_user}",
        "latest": lt["time"] if lt else "深夜",
    }
    idx = hash_pick(m["tinker"]["sessions"], 3)
    fallback = p["roasts"][idx].format(**fmt)
    diag = diagnose(m)
    persona = {
        "id": p["id"],
        "name": p["name"] + ("（见习）" if rookie else ""),
        "tagline": p["tagline"],
        "code": ("夜" if key[0] else "昼") + ("爆" if key[1] else "温") + ("放" if key[2] else "控"),
        "bg": p["bg"], "bg2": p["bg2"], "accent": p["accent"], "glyph": p["glyph"], "dark": p["dark"],
        "rookie": rookie,
        "axes": ax,
        "axis_flags": {"night": key[0], "angry": key[1], "hands_off": key[2]},
        "diagnosis": diag,
        "badges": badges(m),
        "roast": None,
        "roast_fallback": fallback,
        "year": year,
        "numbers": {   # 给 AI 写短评用：只含聚合数字，不含原话/路径/项目名
            "user_msgs": n_user,
            "night_ratio_pct": round(r["night_ratio"] * 100, 1),
            "weekend_ratio_pct": round(r["weekend_ratio"] * 100, 1),
            "latest_time": lt["time"] if lt else None,
            "angry_rate_pct": round(t["angry_rate"] * 100, 1),
            "short_rate_pct": round(d["short_rate"] * 100, 1),
            "continue_count": d["continue_count"],
            "interrupts": t["interrupts"],
            "avg_user_chars": round(d["avg_user_chars"], 1),
            "talk_ratio": round(d["talk_ratio"], 1),
            "active_days": r["active_days"],
            "longest_streak": r["longest_streak"],
            "busiest_day_msgs": (r["busiest_day"] or {}).get("count"),
            "cost_usd": m["spend"]["cost"] if m["spend"]["has_usage"] else None,
            "total_tokens": m["spend"]["total_tokens"] if m["spend"]["has_usage"] else None,
            "sessions": m["tinker"]["sessions"],
            "active_hours": m["tinker"]["total_active_hours"],
            "platforms": m["platforms"],
        },
        "sample_note": "样本少，仅供娱乐" if rookie else None,
    }
    return persona


def hash_pick(n: int, k: int) -> int:
    return (n or 0) % k


# ───────────── 分享文案 ─────────────
PLAT_NAME = {"claude_code": "Claude Code", "codex": "Codex"}


def share_text(m: dict, persona: dict, repo_url: str) -> str:
    r, t, d, s, tk = m["rhythm"], m["temper"], m["reliance"], m["spend"], m["tinker"]
    year = persona.get("year") or ""
    plats = " + ".join(PLAT_NAME.get(p, p) for p in m["platforms"]) or "AI"
    lt = r.get("latest")
    roast = persona.get("roast") or persona["roast_fallback"]
    lines_zh = [
        f"我的 {year} Vibe Coding 人格：【{persona['code']}｜{persona['name']}】",
        f"“{persona['tagline']}”",
        "",
        f"· 和 {plats} 聊了 {m['user_msgs']:,} 句，活跃 {r['active_days']} 天，连续最长 {r['longest_streak']} 天",
    ]
    if lt:
        lines_zh.append(f"· 最晚一次 {lt['time']} 还在发指令，凌晨占比 {r['night_ratio'] * 100:.0f}%")
    lines_zh.append(f"· 骂 AI 命中率 {t['angry_rate'] * 100:.0f}%，打断它 {t['interrupts']} 次")
    if s["has_usage"]:
        lines_zh.append(f"· 烧掉 {fmt_tokens(s['total_tokens'])} token，约 {fmt_money(s['cost'])}（API 价估算），折合 {tea_cups(s['cost']):,} 杯奶茶")
    lines_zh += [
        f"· 和 AI 的关系：{persona['diagnosis']['name']}——{persona['diagnosis']['desc']}",
        "",
        f"AI 点评：{roast}",
        "",
        "你是哪一型？评论区交出你的三字代号（夜/昼 · 爆/温 · 放/控）👇",
        "本地生成，数据不上传，对 Claude Code / Codex 说一句“生成我的 vibe 年报”就行：",
        repo_url,
        "",
        "#VibeCoding #ClaudeCode #Codex #AI编程 #程序员 #年度报告",
    ]
    badge_line = " ".join(f"{b['icon']}{b['title']}" for b in persona["badges"])
    if badge_line:
        lines_zh.insert(len(lines_zh) - 7, f"· 解锁徽章：{badge_line}")

    lines_x = [
        f"My {year} vibe coding persona: 【{persona['code']}】{persona['name']}",
        f"{m['user_msgs']:,} prompts · {r['active_days']} active days · "
        f"{r['night_ratio'] * 100:.0f}% after midnight · {t['angry_rate'] * 100:.0f}% swearing rate",
    ]
    if s["has_usage"]:
        lines_x.append(f"~{fmt_money(s['cost'])} of tokens (API price) / {s['total_tokens'] / 1e6:,.0f}M tokens")
    lines_x += ["", "Which one are you? Local-only, nothing uploaded:", repo_url,
                "", "#vibecoding #ClaudeCode #Codex"]

    ai_prompt = (
        "【发给你的 AI，让它当面吐槽你】\n"
        f"我是“{persona['name']}”：{persona['tagline']}。"
        f"凌晨占比 {r['night_ratio'] * 100:.0f}%，骂人命中率 {t['angry_rate'] * 100:.0f}%，"
        f"短指令占 {d['short_rate'] * 100:.0f}%，一共对你说了 {m['user_msgs']:,} 句。"
        "请用三句话毒舌但不过分地点评我，再给我一条能改善我们关系的建议。"
    )
    return ("===== 小红书 / 朋友圈 =====\n" + "\n".join(lines_zh)
            + "\n\n===== X / Twitter =====\n" + "\n".join(lines_x)
            + "\n\n===== 让 AI 当面吐槽你 =====\n" + ai_prompt + "\n")
