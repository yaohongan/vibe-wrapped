"""统一事件 schema + 公共工具。适配器只负责把平台日志翻译成 Event。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterator, List, Optional

KINDS = ("user_msg", "ai_msg", "tool_call", "usage", "interrupt", "session_meta")


@dataclass
class Event:
    platform: str                 # "claude_code" | "codex"
    session_id: str
    ts: datetime                  # 带时区；适配器输出 UTC，collect 阶段转本地
    kind: str                     # KINDS
    project: Optional[str] = None
    cwd: Optional[str] = None
    text: Optional[str] = None    # 只有 user_msg 保留正文
    n_chars: int = 0              # user_msg / ai_msg 的字符数
    tool_name: Optional[str] = None
    tool_category: Optional[str] = None   # edit / run / read / search / other
    files: List[str] = field(default_factory=list)
    model: Optional[str] = None
    tokens: Optional[Dict[str, int]] = None  # input/output/cache_read/cache_write/reasoning
    is_subagent: bool = False
    version: Optional[str] = None
    raw_ref: str = ""


@dataclass
class ParseStats:
    platform: str
    files: int = 0
    lines: int = 0
    bad_lines: int = 0
    unknown_types: Dict[str, int] = field(default_factory=dict)
    versions: Dict[str, int] = field(default_factory=dict)
    usage_events: int = 0

    def unknown(self, name: str) -> None:
        self.unknown_types[name] = self.unknown_types.get(name, 0) + 1

    def version(self, v: Optional[str]) -> None:
        if v:
            self.versions[v] = self.versions.get(v, 0) + 1

    @property
    def bad_ratio(self) -> float:
        return self.bad_lines / self.lines if self.lines else 0.0

    def as_dict(self) -> dict:
        return {
            "platform": self.platform, "files": self.files, "lines": self.lines,
            "bad_lines": self.bad_lines, "unknown_types": self.unknown_types,
            "versions": self.versions, "usage_events": self.usage_events,
        }


def parse_ts(s) -> Optional[datetime]:
    """ISO 8601（带 Z 或偏移）→ aware UTC datetime。失败返回 None。"""
    if not s or not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def project_name(cwd: Optional[str]) -> Optional[str]:
    if not cwd:
        return None
    if cwd.startswith("file://"):
        from urllib.parse import unquote
        cwd = unquote(cwd[len("file://"):])
    cwd = cwd.rstrip("/\\")
    if not cwd:
        return "/"
    return os.path.basename(cwd.replace("\\", "/")) or cwd


def read_jsonl(path: str, stats: ParseStats) -> Iterator[tuple]:
    """逐行读 jsonl，产出 (行号, dict)。坏行计入 stats，不抛异常。"""
    try:
        fh = open(path, "r", encoding="utf-8", errors="replace")
    except OSError:
        return
    stats.files += 1
    with fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            stats.lines += 1
            try:
                d = json.loads(line)
            except ValueError:
                stats.bad_lines += 1
                continue
            if isinstance(d, dict):
                yield i, d
            else:
                stats.bad_lines += 1
