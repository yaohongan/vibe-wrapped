"""Codex rollout 日志 → Event。

Codex 日志在不同版本里有三代格式并存，这里统一兼容：
  用户原话：event_msg.item_completed(UserMessage)  优先；
            event_msg.user_message                 次选；
            response_item role=user（需剔除注入）   兜底，只在前两者都没有时用。
  AI 回复 ：event_msg.item_completed(AgentMessage) 优先；response_item role=assistant 兜底。
  token   ：event_msg.token_count 优先（用累计值差分去重）；没有时用 token_usage_record。
"""
from __future__ import annotations

import glob
import json
import os
import re
from typing import Iterator, List, Optional, Tuple

from .base import Event, ParseStats, parse_ts, project_name, read_jsonl

REQUEST_MARKER = "## My request for Codex:"
INJECTED_PREFIXES = (
    "<environment_context", "# AGENTS.md instructions", "<turn_aborted",
    "<recommended_plugins", "<external_codex_apps", "<goal_context",
    "The following is the Codex", "<user_instructions", "<permissions",
    "<skill", "<subagent", "<INSTRUCTIONS", "<collaboration_mode",
    "# Files mentioned by the user", "# Files pasted by the user",
    "# Context from my IDE setup",
)
PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.M)
READ_CMD_RE = re.compile(r"^(?:sudo\s+)?(?:cat|sed\s+-n|head|tail|ls|wc|nl|bat|less|stat|file|pwd)\b")
SEARCH_CMD_RE = re.compile(r"^(?:sudo\s+)?(?:rg|grep|find|fd|ag|git\s+(?:grep|log|show|diff|status))\b")


def default_roots() -> List[str]:
    home = os.environ.get("CODEX_HOME") or "~/.codex"
    base = os.path.expanduser(home)
    return [os.path.join(base, "sessions"), os.path.join(base, "archived_sessions")]


def find_files(roots: Optional[List[str]] = None) -> List[str]:
    sessions, archived = (roots or default_roots())[:2]
    files = {}
    for f in glob.glob(os.path.join(archived, "rollout-*.jsonl")):
        files[os.path.basename(f)] = f
    # sessions/ 与 archived_sessions/ 同名文件以 sessions/ 为准
    for f in glob.glob(os.path.join(sessions, "*", "*", "*", "rollout-*.jsonl")):
        files[os.path.basename(f)] = f
    return [files[k] for k in sorted(files)]


def clean_user_text(text: str) -> Optional[str]:
    if not isinstance(text, str):
        return None
    if REQUEST_MARKER in text:
        text = text.split(REQUEST_MARKER, 1)[1]
    text = text.strip()
    if not text or text.startswith(INJECTED_PREFIXES):
        return None
    return text


def _content_text(content) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for c in content or []:
        if isinstance(c, dict) and isinstance(c.get("text"), str):
            parts.append(c["text"])
    return "\n".join(parts)


def _shell_category(cmd: str) -> str:
    cmd = cmd.strip()
    # 取管道/&& 之前的第一条命令判断
    first = re.split(r"\s*(?:&&|\|\||;|\|)\s*", cmd, maxsplit=1)[0]
    first = re.sub(r"^(?:cd\s+\S+\s*&&\s*)", "", first)
    if SEARCH_CMD_RE.match(first):
        return "search"
    if READ_CMD_RE.match(first):
        return "read"
    return "run"


def parse_file(path: str, stats: ParseStats) -> Iterator[Event]:
    fallback_sid = os.path.splitext(os.path.basename(path))[0]
    sid, cwd, sub, ver, model = fallback_sid, None, False, None, None
    cand = {"ic_user": [], "ev_user": [], "ri_user": [],
            "ic_ast": [], "ri_ast": []}
    tools: List[Event] = []
    interrupts: List[Event] = []
    tc_events: List[Event] = []     # token_count 来源
    tur_events: List[Event] = []    # token_usage_record 来源
    prev_total = None
    prev_tur_total = None
    prev_tot_dict: dict = {}
    meta_ev: Optional[Event] = None

    def mk(kind, ts, ln, **kw) -> Event:
        return Event(platform="codex", session_id=sid, ts=ts, kind=kind,
                     project=project_name(cwd), cwd=cwd, is_subagent=sub,
                     version=ver, raw_ref=f"{path}:{ln}", **kw)

    for ln, d in read_jsonl(path, stats):
        typ = d.get("type")
        p = d.get("payload") if isinstance(d.get("payload"), dict) else {}
        pt = p.get("type")
        ts = parse_ts(d.get("timestamp"))
        if ts is None:
            continue

        if typ == "session_meta":
            sid = p.get("id") or p.get("session_id") or sid
            cwd = p.get("cwd") or cwd
            ver = p.get("cli_version") or ver
            stats.version(ver)
            src = p.get("source")
            if isinstance(src, dict) and "subagent" in src:
                sub = True
            meta_ev = mk("session_meta", ts, ln)
            continue

        if typ == "turn_context":
            model = p.get("model") or model
            cwd = p.get("cwd") or cwd
            continue

        if typ == "event_msg":
            if pt == "item_completed":
                item = p.get("item") if isinstance(p.get("item"), dict) else {}
                it = item.get("type")
                if it == "UserMessage":
                    t = clean_user_text(_content_text(item.get("content")))
                    if t:
                        cand["ic_user"].append(mk("user_msg", ts, ln, text=t, n_chars=len(t)))
                elif it == "AgentMessage":
                    t = _content_text(item.get("content"))
                    if t.strip():
                        cand["ic_ast"].append(mk("ai_msg", ts, ln, n_chars=len(t), model=model))
            elif pt == "user_message":
                t = clean_user_text(p.get("message"))
                if t:
                    cand["ev_user"].append(mk("user_msg", ts, ln, text=t, n_chars=len(t)))
            elif pt == "turn_aborted":
                interrupts.append(mk("interrupt", ts, ln))
            elif pt == "token_count":
                info = p.get("info")
                if not isinstance(info, dict):
                    continue
                tot = info.get("total_token_usage") or {}
                last = info.get("last_token_usage") or {}
                tt = int(tot.get("total_tokens") or 0)
                if prev_total is not None and tt == prev_total:
                    continue            # 重复发射的同一条
                src = last
                if prev_total is not None and 0 < tt - prev_total and tt - prev_total != int(last.get("total_tokens") or -1):
                    # 累计差分更可靠（last 缺失或中间漏了几条）
                    src = {k: int(tot.get(k) or 0) - int(prev_tot_dict.get(k) or 0) for k in tot}
                prev_total, prev_tot_dict = tt, dict(tot)
                tc_events.append(mk("usage", ts, ln, model=model, tokens=norm_tokens(src)))
            continue

        if typ == "token_usage_record":
            u = p.get("usage") or {}
            tt = int((p.get("thread_token_usage") or {}).get("total_tokens") or 0)
            if tt and tt == prev_tur_total:
                continue
            prev_tur_total = tt or prev_tur_total
            tur_events.append(mk("usage", ts, ln, model=model, tokens=norm_tokens(u)))
            continue

        if typ == "response_item":
            if pt == "message":
                role = p.get("role")
                t = _content_text(p.get("content"))
                if role == "user":
                    c = clean_user_text(t)
                    if c:
                        cand["ri_user"].append(mk("user_msg", ts, ln, text=c, n_chars=len(c)))
                elif role == "assistant" and t.strip():
                    cand["ri_ast"].append(mk("ai_msg", ts, ln, n_chars=len(t), model=model))
            elif pt == "function_call":
                name = p.get("name") or "function"
                args = p.get("arguments")
                try:
                    a = json.loads(args) if isinstance(args, str) else (args or {})
                except ValueError:
                    a = {}
                cmd = a.get("cmd") or a.get("command") or ""
                if isinstance(cmd, list):
                    cmd = " ".join(str(x) for x in cmd)
                cat = _shell_category(cmd) if isinstance(cmd, str) and cmd else "run"
                tools.append(mk("tool_call", ts, ln, tool_name=name, tool_category=cat, model=model))
            elif pt == "custom_tool_call":
                name = p.get("name") or "custom"
                inp = p.get("input") if isinstance(p.get("input"), str) else ""
                files = PATCH_FILE_RE.findall(inp) if name == "apply_patch" else []
                cat = "edit" if name == "apply_patch" else "other"
                tools.append(mk("tool_call", ts, ln, tool_name=name, tool_category=cat,
                                files=[f.strip() for f in files], model=model))
            continue

        if typ not in ("compacted", "world_state", "inter_agent_communication_metadata"):
            stats.unknown(str(typ))

    out: List[Event] = []
    if meta_ev:
        out.append(meta_ev)
    for key in ("ic_user", "ev_user", "ri_user"):     # 取第一个有数据的来源，避免重复
        if cand[key]:
            out.extend(cand[key])
            break
    out.extend(cand["ic_ast"] or cand["ri_ast"])
    out.extend(tools)
    out.extend(interrupts)
    usage = tc_events or tur_events
    stats.usage_events += len(usage)
    out.extend(usage)
    out.sort(key=lambda e: e.ts)
    for e in out:
        # session_meta 在 turn_context 之前创建，补上最终 cwd/project
        if e.cwd is None and cwd:
            e.cwd, e.project = cwd, project_name(cwd)
        yield e


def norm_tokens(u: dict) -> dict:
    inp = int(u.get("input_tokens") or 0)
    cached = int(u.get("cached_input_tokens") or 0)
    return {
        "input": max(inp - cached, 0),     # cached 是 input 的一部分，不重复计
        "output": int(u.get("output_tokens") or 0),
        "cache_read": cached,
        "cache_write": int(u.get("cache_write_input_tokens") or 0),
        "reasoning": int(u.get("reasoning_output_tokens") or 0),
    }


def collect(roots: Optional[List[str]] = None) -> Tuple[List[Event], ParseStats]:
    stats = ParseStats("codex")
    events: List[Event] = []
    for f in find_files(roots):
        events.extend(parse_file(f, stats))
    return events, stats
