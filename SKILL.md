---
name: vibe-wrapped
description: 生成 Vibe Coding 人格年报。读取本机 Claude Code 和 Codex 会话日志，本地统计作息、脾气、依赖度、花费，判定人格类型并输出竖版分享海报和可复制文案。当用户说“vibe 年报”“wrapped”“我的 AI 编程年报”“vibe-wrapped”时使用。
---

# vibe-wrapped：Vibe Coding 人格年报

所有统计都由本目录的 Python 脚本完成，全程本地，不联网。你（Agent）只负责：运行脚本、写一句毒舌短评、把结果交给用户。不要自己数数据，不要改脚本算出来的数字。

下文 `<skill>` 指本 SKILL.md 所在目录（若无法确定，用 `~/.claude/skills/vibe-wrapped`、`~/.agents/skills/vibe-wrapped` 或 `~/.codex/skills/vibe-wrapped` 中存在的那个）。

## 步骤

1. 检查环境
   - 运行 `python3 <skill>/scripts/wrapped.py doctor`：报告找到哪些平台的日志、渲染器（Chrome / Playwright）是否可用。需要 Python ≥3.9，只用标准库。
   - 没有渲染器时不要自己装东西，告诉用户：可以只出 HTML 自行截图（加 `--html-only`），或安装 Chrome。

2. 统计
   - 运行 `python3 <skill>/scripts/wrapped.py stats --out ~/vibe-wrapped-out`
   - 用户指定了范围就加 `--year 2026` 或 `--since YYYY-MM-DD --until YYYY-MM-DD`，要全部历史加 `--all`；项目名和文件名默认已匿名（项目 A/B、*.tsx）；用户明确要显示真实项目名才加 `--show-projects`。
   - 终端提示“日志格式可能更新了”时，原样转告用户。

3. 写短评（你唯一需要创作的内容）
   - 读 `~/vibe-wrapped-out/persona.json`（只含聚合数字，没有原话）。
   - 写一句 ≤40 个汉字的中文毒舌短评：好笑、引用其中一个具体数字、不人身攻击、不涉及性别/外貌/地域。
   - 用 `python3 <skill>/scripts/wrapped.py roast --text "<短评>"` 写回，不要直接改 JSON。
   - 用户说不要 AI 短评时跳过，脚本会用预设短评。

4. 渲染
   - 运行 `python3 <skill>/scripts/wrapped.py render --out ~/vibe-wrapped-out`
   - 生成 `poster-3x4.png`（小红书/朋友圈/X）、`poster-9x16.png`（故事/全屏）、同名 HTML，以及 `share.txt`（小红书文案、X 文案、让 AI 当面吐槽你的提示词）。
   - 只要一张图加 `--size 1080x1440` 或 `--size 1080x1920`。

5. 交付
   - 先告诉用户：海报上会出现一句脱敏后的“最暴躁原话”（项目名已默认匿名），问一次是否要去掉原话。要去掉就重新 render，加 `--no-quotes`。
   - 然后给出：人格类型、3 个最有梗的数字、海报路径、share.txt 里的文案。
   - 提醒：花费是按 API 标准价估算的，订阅用户实际支出不同。

## 禁止事项
- 不要把日志内容、原话、路径发到任何网络服务。
- 不要读取认证文件（`auth.json`、`.credentials.json` 等），脚本也不会读。
- 不要编造脚本没有给出的数字。
