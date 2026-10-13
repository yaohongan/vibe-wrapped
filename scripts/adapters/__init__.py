"""平台适配器：自动发现本机有哪些平台的日志。"""
from . import claude_code, codex

ADAPTERS = {"claude_code": claude_code, "codex": codex}


def detect():
    """返回 {平台: 日志文件数}，只含本机存在日志的平台。"""
    found = {}
    for name, mod in ADAPTERS.items():
        n = len(mod.find_files())
        if n:
            found[name] = n
    return found
