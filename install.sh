#!/usr/bin/env bash
# 把 vibe-wrapped 复制（不用软链，Codex 会跳过软链）到各平台的 skills 目录。
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="vibe-wrapped"
want_claude=0; want_codex=0

case "${1:-all}" in
  --claude) want_claude=1 ;;
  --codex)  want_codex=1 ;;
  all|--all|"") want_claude=1; want_codex=1 ;;
  *) echo "用法: ./install.sh [--claude | --codex]"; exit 1 ;;
esac

copy_to() {
  local dest="$1/$NAME"
  mkdir -p "$1"
  rm -rf "$dest"
  mkdir -p "$dest"
  # 只复制运行需要的文件
  for item in SKILL.md README.md scripts templates data; do
    [ -e "$SRC/$item" ] && cp -R "$SRC/$item" "$dest/"
  done
  find "$dest" -name '__pycache__' -type d -prune -exec rm -rf {} +
  echo "✓ 已安装到 $dest"
}

installed=0
if [ "$want_claude" = 1 ]; then
  copy_to "$HOME/.claude/skills"; installed=1
fi
if [ "$want_codex" = 1 ]; then
  copy_to "$HOME/.agents/skills"                       # Codex 新版
  copy_to "${CODEX_HOME:-$HOME/.codex}/skills"         # Codex 旧版兼容
  installed=1
fi

echo
echo "完成。请重启 Claude Code / Codex。"
echo "  Claude Code：直接说“生成我的 vibe 年报”"
echo "  Codex：输入 /skills 或 \$vibe-wrapped"
echo "  旧版 Codex 看不到 skill 时，在 ~/.codex/config.toml 加：[features] skills = true"
echo "不装 Skill 也能用：python3 $SRC/scripts/wrapped.py all"
