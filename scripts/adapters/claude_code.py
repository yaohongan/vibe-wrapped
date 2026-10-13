"""Claude Code 会话日志 → Event。

只读 projects/ 下的 *.jsonl（白名单），不碰认证文件。所有字段用 .get() 取值，
未知 type 忽略并计数——官方说明日志是内部格式，每个版本都可能变。
"""
from __future__ import annotations

import glob
import os
from typing import Iterator, List, Optional, Tuple

from .base import Event, ParseStats, parse_ts, project_name, read_jsonl

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
READ_TOOLS = {"Read", "NotebookRead"}
SEARCH_TOOLS = {"Grep", "Glob", "WebSearch", "WebFetch", "ToolSearch"}
RUN_TOOLS = {"Bash", "BashOutput", "KillShell"}

# 这些前缀开头的 user 文本是系统/斜杠命令注入，不是人打的字
INJECTED_PREFIXES = (
    "<command-name>", "<command-message>", "<command-args>", "<local-command",
    "<system-reminder>", "<task-notification", "<bash-input>", "<bash-stdout>",
    "<bash-output>", "<ide_", "Caveat:", "[Request interrupted",
    "This session is being continued", "Base directory for this skill",
)
INTERRUPT_PREFIX = "[Request interrupted"


def default_roots() -> List[str]:
    roots = []
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    if cfg:
        for p in cfg.split(","):
            roots.append(os.path.join(os.path.expanduser(p.strip()), "projects"))
    roots.append(os.path.expanduser("~/.claude/projects"))
    roots.append(os.path.expanduser("~/.config/claude/projects"))
    seen, out = set(), []
    for r in roots:
        rp = os.path.realpath(r)
        if rp not in seen and os.path.isdir(rp):
            seen.add(rp)
            out.append(rp)
    return out


def find_files(roots: Optional[List[str]] = None) -> List[str]:
    files = set()
    for root in roots or default_roots():
        files.update(glob.glob(os.path.join(root, "*", "*.jsonl")))
        files.update(glob.glob(os.path.join(root, "*", "*", "subagents", "*.jsonl")))
    return sorted(files)


def tool_category(name: str) -> str:
    if name in EDIT_TOOLS:
        return "edit"
    if name in RUN_TOOLS:
        return "run"
    if name in READ_TOOLS:
        return "read"
    if name in SEARCH_TOOLS:
        return "search"
    return "other"


def human_text(msg: dict) -> Tuple[Optional[str], bool]:
    """返回 (人打的字 or None, 是否被用户打断)。"""
    content = msg.get("content")
    if isinstance(content, str):
        parts = [content]
    elif isinstance(content, list):
        # 含 tool_result 的整条都不是人说的话
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None, False
        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
    else:
        return None, False
    text = "\n".join(p for p in parts if isinstance(p, str)).strip()
    if not text:
        return None, False
    if text.startswith(INTERRUPT_PREFIX):
        return None, True
    if text.startswith(INJECTED_PREFIXES):
        return None, False
    return text, False


def parse_file(path: str, stats: ParseStats) -> Iterator[Event]:
    in_subagent_dir = f"{os.sep}subagents{os.sep}" in path
    fallback_sid = os.path.splitext(os.path.basename(path))[0]
    usage_best = {}   # dedupe key -> (output_tokens, Event)，同一条回复取最完整的一行
    out: List[Event] = []
    meta_emitted = False

    for ln, d in read_jsonl(path, stats):
        typ = d.get("type")
        if typ not in ("user", "assistant"):
            if typ is not None:
                stats.unknown(str(typ))
            continue
        ts = parse_ts(d.get("timestamp"))
        if ts is None:
            continue
        sid = d.get("sessionId") or fallback_sid
        cwd = d.get("cwd")
        proj = project_name(cwd)
        sub = bool(d.get("isSidechain")) or in_subagent_dir
        ver = d.get("version")
        stats.version(ver)
        ref = f"{path}:{ln}"
        base = dict(platform="claude_code", session_id=sid, ts=ts, project=proj,
                    cwd=cwd, is_subagent=sub, version=ver, raw_ref=ref)

        if not meta_emitted and cwd:
            out.append(Event(kind="session_meta", **base))
            meta_emitted = True

        msg = d.get("message") or {}
        if typ == "user":
            if d.get("isMeta"):
                continue
            origin = d.get("origin")
            if isinstance(origin, dict) and origin.get("kind") not in (None, "human"):
                continue
            text, interrupted = human_text(msg)
            if interrupted:
                out.append(Event(kind="interrupt", **base))
            elif text:
                out.append(Event(kind="user_msg", text=text, n_chars=len(text), **base))
            continue

        # assistant
        model = msg.get("model")
        if model == "<synthetic>":
            continue
        for blk in msg.get("content") or []:
            if not isinstance(blk, dict):
                continue
            bt = blk.get("type")
            if bt == "text":
                t = blk.get("text") or ""
                if t.strip():
                    out.append(Event(kind="ai_msg", n_chars=len(t), model=model, **base))
            elif bt == "tool_use":
                name = blk.get("name") or "?"
                inp = blk.get("input") if isinstance(blk.get("input"), dict) else {}
                files = []
                for k in ("file_path", "notebook_path", "path"):
                    v = inp.get(k)
                    if isinstance(v, str) and v:
                        files.append(v)
                        break
                out.append(Event(kind="tool_call", tool_name=name,
                                 tool_category=tool_category(name),
                                 files=files, model=model, **base))
        u = msg.get("usage")
        if isinstance(u, dict):
            key = (msg.get("id"), d.get("requestId")) if msg.get("id") else ("line", ref)
            toks = {
                "input": int(u.get("input_tokens") or 0),
                "output": int(u.get("output_tokens") or 0),
                "cache_read": int(u.get("cache_read_input_tokens") or 0),
                "cache_write": int(u.get("cache_creation_input_tokens") or 0),
                "reasoning": 0,
            }
            ev = Event(kind="usage", tokens=toks, model=model, **base)
            prev = usage_best.get(key)
            if prev is None or toks["output"] >= prev[0]:
                usage_best[key] = (toks["output"], ev)

    for _, ev in usage_best.values():
        out.append(ev)
        stats.usage_events += 1
    out.sort(key=lambda e: e.ts)
    for ev in out:
        yield ev


def collect(roots: Optional[List[str]] = None) -> Tuple[List[Event], ParseStats]:
    stats = ParseStats("claude_code")
    events: List[Event] = []
    for f in find_files(roots):
        events.extend(parse_file(f, stats))
    return events, stats
