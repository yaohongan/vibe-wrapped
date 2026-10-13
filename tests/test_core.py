"""核心单测（标准库 unittest）。运行：python3 -m unittest discover -s tests"""
import json, os, socket, sys, tempfile, unittest
from datetime import date, datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))

import metrics, persona, redact, pricing  # noqa: E402
from adapters import claude_code, codex   # noqa: E402
from adapters.base import Event, ParseStats  # noqa: E402

UTC8 = timezone(timedelta(hours=8))


def write(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write((r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)) + "\n")


class AdapterTests(unittest.TestCase):
    def test_claude_user_text_and_usage_dedupe(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.jsonl")
            base = {"sessionId": "s1", "cwd": "/a/proj", "version": "9", "isSidechain": False}
            write(p, [
                dict(base, type="user", timestamp="2026-03-01T16:30:00Z", uuid="1",
                     message={"role": "user", "content": "你好，帮我改下"}),
                dict(base, type="user", timestamp="2026-03-01T16:30:01Z", uuid="2",
                     message={"role": "user", "content": [{"type": "tool_result", "content": "x"}]}),
                dict(base, type="user", timestamp="2026-03-01T16:30:02Z", uuid="3", isMeta=True,
                     message={"role": "user", "content": "meta"}),
                dict(base, type="user", timestamp="2026-03-01T16:30:03Z", uuid="4",
                     message={"role": "user", "content": "<command-name>/clear</command-name>"}),
                dict(base, type="user", timestamp="2026-03-01T16:30:04Z", uuid="5",
                     message={"role": "user", "content": [{"type": "text", "text": "[Request interrupted by user]"}]}),
                # 同一条回复拆成两行，usage 重复
                dict(base, type="assistant", timestamp="2026-03-01T16:31:00Z", requestId="r1",
                     message={"id": "m1", "model": "claude-sonnet-5-5",
                              "content": [{"type": "text", "text": "好"}],
                              "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 100}}),
                dict(base, type="assistant", timestamp="2026-03-01T16:31:01Z", requestId="r1",
                     message={"id": "m1", "model": "claude-sonnet-5-5",
                              "content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": "/a/proj/x.py"}}],
                              "usage": {"input_tokens": 10, "output_tokens": 50, "cache_read_input_tokens": 100}}),
                "{坏行",
            ])
            st = ParseStats("claude_code")
            ev = list(claude_code.parse_file(p, st))
            kinds = [e.kind for e in ev]
            self.assertEqual(kinds.count("user_msg"), 1)
            self.assertEqual(kinds.count("interrupt"), 1)
            self.assertEqual(st.bad_lines, 1)
            usage = [e for e in ev if e.kind == "usage"]
            self.assertEqual(len(usage), 1)
            self.assertEqual(usage[0].tokens["output"], 50)       # 取最完整的一行
            tool = [e for e in ev if e.kind == "tool_call"][0]
            self.assertEqual((tool.tool_category, tool.files), ("edit", ["/a/proj/x.py"]))

    def test_codex_new_and_old_format(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "rollout-x.jsonl")
            write(p, [
                {"timestamp": "2026-03-01T01:00:00Z", "type": "session_meta",
                 "payload": {"id": "c1", "cwd": "/w/p", "cli_version": "1", "source": "vscode"}},
                {"timestamp": "2026-03-01T01:00:01Z", "type": "turn_context",
                 "payload": {"model": "gpt-5.4", "cwd": "/w/p"}},
                # 新版用户消息
                {"timestamp": "2026-03-01T01:00:02Z", "type": "event_msg",
                 "payload": {"type": "item_completed", "item": {"type": "UserMessage",
                             "content": [{"type": "text", "text": "继续"}]}}},
                # 老版注入 + 同一句（不应重复计）
                {"timestamp": "2026-03-01T01:00:02Z", "type": "response_item",
                 "payload": {"type": "message", "role": "user",
                             "content": [{"type": "input_text", "text": "# Context from my IDE setup:\n## My request for Codex:\n继续"}]}},
                {"timestamp": "2026-03-01T01:00:03Z", "type": "response_item",
                 "payload": {"type": "message", "role": "user",
                             "content": [{"type": "input_text", "text": "<environment_context>x</environment_context>"}]}},
                {"timestamp": "2026-03-01T01:00:04Z", "type": "response_item",
                 "payload": {"type": "custom_tool_call", "name": "apply_patch",
                             "input": "*** Begin Patch\n*** Update File: /w/p/a.ts\n@@\n*** End Patch"}},
                {"timestamp": "2026-03-01T01:00:05Z", "type": "event_msg",
                 "payload": {"type": "token_count", "info": {
                     "total_token_usage": {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 10, "total_tokens": 110},
                     "last_token_usage": {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 10, "total_tokens": 110}}}},
                {"timestamp": "2026-03-01T01:00:06Z", "type": "event_msg",   # 重复发射
                 "payload": {"type": "token_count", "info": {
                     "total_token_usage": {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 10, "total_tokens": 110},
                     "last_token_usage": {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 10, "total_tokens": 110}}}},
                {"timestamp": "2026-03-01T01:00:07Z", "type": "event_msg", "payload": {"type": "turn_aborted"}},
            ])
            ev = list(codex.parse_file(p, ParseStats("codex")))
            self.assertEqual(sum(e.kind == "user_msg" for e in ev), 1)
            u = [e for e in ev if e.kind == "usage"]
            self.assertEqual(len(u), 1)
            self.assertEqual(u[0].tokens, {"input": 60, "output": 10, "cache_read": 40,
                                           "cache_write": 0, "reasoning": 0})
            self.assertEqual(u[0].model, "gpt-5.4")
            t = [e for e in ev if e.kind == "tool_call"][0]
            self.assertEqual(t.files, ["/w/p/a.ts"])
            self.assertEqual(sum(e.kind == "interrupt" for e in ev), 1)


def mk(ts, text, platform="codex", sid="s", **kw):
    return Event(platform=platform, session_id=sid, ts=ts, kind="user_msg",
                 text=text, n_chars=len(text), project="p", **kw)


class MetricsTests(unittest.TestCase):
    def events(self):
        base = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)  # 北京 20:00
        ev = [mk(base + timedelta(minutes=i), t) for i, t in
              enumerate(["继续", "不对！！", "wrong", "no problem", "把这个改成蓝色"])]
        # 北京时间凌晨 4:37（UTC 前一天 20:37）
        ev.append(mk(datetime(2026, 3, 2, 20, 37, tzinfo=timezone.utc), "再来一次"))
        return ev

    def test_core_metrics(self):
        m = metrics.compute(self.events(), tz=UTC8)
        self.assertEqual(m["user_msgs"], 6)
        self.assertEqual(m["rhythm"]["latest"]["time"], "04:37")
        self.assertAlmostEqual(m["rhythm"]["night_ratio"], 1 / 6)
        # “不对！！” 与 “wrong” 命中；“no problem” 不命中
        self.assertEqual(m["temper"]["angry_count"], 2)
        self.assertEqual(m["reliance"]["continue_count"], 1)

    def test_deterministic(self):
        a = json.dumps(metrics.compute(self.events(), tz=UTC8), sort_keys=True, default=str)
        b = json.dumps(metrics.compute(list(reversed(self.events())), tz=UTC8), sort_keys=True, default=str)
        self.assertEqual(a, b)

    def test_window(self):
        m = metrics.compute(self.events(), tz=UTC8, since=date(2026, 3, 3), until=date(2026, 3, 3))
        self.assertEqual(m["user_msgs"], 1)


class MiscTests(unittest.TestCase):
    def test_redact(self):
        s = redact.redact_text("见 https://a.com/x 邮箱 me@x.com 路径 /Users/bob/code/app sk-abcdef1234567890 手机 13800138000")
        for bad in ("a.com", "me@x.com", "/Users/bob", "sk-abcdef", "13800138000"):
            self.assertNotIn(bad, s)
        self.assertEqual(redact.file_label("/a/b/Page.tsx", True), "*.tsx")

    def test_pricing(self):
        c, exact, ok = pricing.cost({"input": 1_000_000, "output": 1_000_000}, "gpt-5.4")
        self.assertAlmostEqual(c, 17.5)
        self.assertTrue(ok and exact)
        c2, exact2, ok2 = pricing.cost({"input": 1}, "totally-unknown")
        self.assertFalse(ok2)

    def test_all_eight_personas_reachable(self):
        seen = set()
        for n in (0, 100):
            for g in (0, 100):
                for l in (0, 100):
                    seen.add(persona.PERSONAS[(n >= persona.N_HIGH, g >= persona.G_HIGH, l >= persona.L_HIGH)]["id"])
        self.assertEqual(len(seen), 8)
        for p in persona.PERSONAS.values():
            self.assertEqual(len(p["roasts"]), 3)

    def test_no_network_needed(self):
        orig = socket.socket.connect
        def boom(*a, **k): raise AssertionError("network used")
        socket.socket.connect = boom
        try:
            m = metrics.compute(MetricsTests().events(), tz=UTC8)
            p = persona.build(m, 2026)
            self.assertIn("name", p)
            persona.share_text(m, p, "github.com/x/y")
        finally:
            socket.socket.connect = orig

    def test_persona_json_has_no_quotes(self):
        m = metrics.compute(MetricsTests().events(), tz=UTC8)
        txt = json.dumps(persona.build(m, 2026), ensure_ascii=False)
        self.assertNotIn("不对", txt)
        self.assertNotIn("wrong", txt)


if __name__ == "__main__":
    unittest.main()
