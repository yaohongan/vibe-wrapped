"""8 型人格合成数据检查：每一型都必须能从“事件”端到端落到对应人格，并能渲染海报。"""
import itertools, os, sys, unittest
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))

import metrics, persona, render  # noqa: E402
from adapters.base import Event  # noqa: E402

TZ = timezone(timedelta(hours=8))
N_MSGS = 80                                   # ≥50，避免“见习”

EXPECT = {  # (夜, 爆, 放) → 人格 id
    (1, 1, 1): "night-angry-hands-off", (1, 1, 0): "night-angry-control",
    (1, 0, 1): "night-calm-hands-off",  (1, 0, 0): "night-calm-control",
    (0, 1, 1): "day-angry-hands-off",   (0, 1, 0): "day-angry-control",
    (0, 0, 1): "day-calm-hands-off",    (0, 0, 0): "day-calm-control",
}


def synth(night, angry, hands_off):
    """造 N_MSGS 条用户消息：night 控制发送时段，angry 控制火药味，hands_off 控制短指令与工具量。"""
    ev, sid = [], "synth"
    for i in range(N_MSGS):
        day = 2 + (i % 5)                              # 2026-03-02(周一)…03-06(周五)，无周末
        hour = 2 if (night and i % 3 == 0) else 14     # 夜型：1/3 在凌晨 2 点
        ts = datetime(2026, 3, day, hour, i % 60, tzinfo=TZ)
        is_angry = angry and i % 4 == 0                # 25% 暴躁
        if hands_off:
            text = "不对！！" if is_angry else "继续"
        else:
            text = ("不对，这里的逻辑写错了，重来一遍并解释原因" if is_angry
                    else "请把这个函数重构一下，并补充边界条件的单元测试")
        ev.append(Event(platform="codex", session_id=sid, ts=ts, kind="user_msg",
                        text=text, n_chars=len(text), project="demo"))
        if hands_off:   # 放手型：每句话 AI 干很多活、说很多话
            for k in range(12):
                ev.append(Event(platform="codex", session_id=sid, ts=ts + timedelta(seconds=k + 1),
                                kind="tool_call", tool_name="exec_command", tool_category="run"))
            ev.append(Event(platform="codex", session_id=sid, ts=ts + timedelta(seconds=20),
                            kind="ai_msg", n_chars=400))
    return ev


class EightPersonas(unittest.TestCase):
    def test_each_persona_reachable(self):
        for combo, want in EXPECT.items():
            m = metrics.compute(synth(*combo), tz=TZ)
            p = persona.build(m, 2026)
            self.assertEqual(p["id"], want, f"{combo} → {p['id']} axes={p['axes']}")
            self.assertFalse(p["rookie"])

    def test_each_persona_renders(self):
        for combo in EXPECT:
            m = metrics.compute(synth(*combo), tz=TZ)
            p = persona.build(m, 2026)
            for size in ("1080x1440", "1080x1920"):
                html = render.build_html(m, p, render.Options(), size)
                self.assertIn(p["name"], html)
                self.assertNotIn("{{", html)        # 模板占位符都被替换

    def test_eight_distinct_names_and_colors(self):
        names = {p["name"] for p in persona.PERSONAS.values()}
        bgs = {p["bg"] for p in persona.PERSONAS.values()}
        self.assertEqual((len(names), len(bgs)), (8, 8))


if __name__ == "__main__":
    unittest.main()
