---
name: vibe-wrapped
description: 生成 Vibe Check 人格报告。读取本机 Claude Code 和 Codex 会话日志，本地统计作息、脾气、依赖度、花费，判定人格并输出竖版分享海报和文案。一句话指定时间维度：本周、本月（近30天）、近三个月、近半年、今年、全部，或自定义日期；不指定默认近30天。用户说“vibe 报告”“生成我的 vibe 本周报告”“vibe check”“wrapped”“我的 AI 编程报告”时使用。
---

# vibe-wrapped：Vibe Check 人格报告

所有统计都由本目录的 Python 脚本完成，全程本地，不联网。你（Agent）只负责：解析用户要的时间范围、运行脚本、写一句毒舌短评、把结果交给用户。不要自己数数据，不要改脚本算出来的数字。

下文 `<skill>` 指本 SKILL.md 所在目录（若无法确定，用 `~/.claude/skills/vibe-wrapped`、`~/.agents/skills/vibe-wrapped` 或 `~/.codex/skills/vibe-wrapped` 中存在的那个）。

## 支持的时间维度（一句话直接说，不用再问）

| 用户怎么说 | `--range` | 含义 |
|---|---|---|
| 本周 / 一周 / 近 7 天 | `week` | 近 7 天 |
| 本月 / 一个月 / 近 30 天 | `month` | 近 30 天 |
| 近三个月 / 季度 | `quarter` | 近 90 天 |
| 近半年 / 半年 | `halfyear` | 近 180 天 |
| 今年 / 一年 / 年度 | `year` | 今年 1/1 至今 |
| 全部 / 有日志以来 | `all` | 全部历史 |
| 指定日期 | `--since YYYY-MM-DD --until YYYY-MM-DD` | 自定义 |
| 没说时间 | 不加参数（`auto`） | 近 30 天；日志不足 30 天则取全部 |

**不要先反问时间。** 用户说了就按上表，没说就用默认，出完图后再告诉用户可以换成哪些维度。

## 步骤

1. 检查环境
   - 运行 `python3 <skill>/scripts/wrapped.py doctor`：报告找到哪些平台的日志、渲染器（Chrome / Playwright）是否可用。需要 Python ≥3.9，只用标准库。
   - 没有渲染器时不要自己装东西，告诉用户：可以只出 HTML 自行截图（加 `--html-only`），或安装 Chrome。

2. 统计
   - 运行 `python3 <skill>/scripts/wrapped.py stats --range <key> --out ~/vibe-wrapped-out`
   - 项目名和文件名默认已匿名（项目 A/B、*.tsx）；用户明确要显示真实项目名才加 `--show-projects`。
   - 输出里的“时间范围”和用户消息数要转告用户；消息数 <50 时人格会标“见习”，说明样本少，可建议换更长的范围。
   - 终端提示“日志格式可能更新了”时，原样转告用户。

3. 写短评（你唯一需要创作的内容）
   - 读 `~/vibe-wrapped-out/persona.json`（只含聚合数字，没有原话）。
   - 写一句 ≤40 个汉字的中文毒舌短评：好笑、引用其中一个具体数字、不人身攻击、不涉及性别/外貌/地域。
   - 写回时**用 stdin + 带引号的 heredoc**，避免 shell 把 `$1,093`、反引号、引号吞掉：

     ```bash
     python3 <skill>/scripts/wrapped.py roast --stdin <<'EOF'
     246 天烧掉 $1,093，换来 119 次打断。
     EOF
     ```
   - 不要直接改 JSON。
   - 用户说不要 AI 短评时跳过，脚本会用预设短评。

4. 渲染
   - 运行 `python3 <skill>/scripts/wrapped.py render --out ~/vibe-wrapped-out`
   - 生成 `poster-3x4.png`（小红书/朋友圈/X）、`poster-9x16.png`（故事/全屏）、同名 HTML，以及 `share.txt`（小红书文案、X 文案、让 AI 当面吐槽你的提示词）。
   - 只要一张图加 `--size 1080x1440` 或 `--size 1080x1920`。

5. 交付（**必须直接把图显示在回复里**，不要只给文件路径）
   - `render` 结束时会打印一段“交付块”（`![海报](绝对路径)` 加文件夹链接）。**把这段 Markdown 原样贴进你的回复**，让用户一眼就看到海报，再从链接跳转到文件夹。
   - 如果你的界面有“向用户展示文件/图片”的工具（例如 SendUserFile），也用它把 `poster-3x4.png` 直接展示出来。
   - 如果界面是纯终端、内嵌图片显示不出来，就改用 `render --open`（或 `all --open`），让系统看图软件打开海报。
   - 然后给出：时间范围、人格（含三字代号）、3 个最有梗的数字、海报路径、share.txt 里的文案。
   - 提醒：海报上会出现一句脱敏后的“最暴躁原话”，项目名已匿名；用户想去掉原话就重新 render 加 `--no-quotes`。
   - 提醒：花费是按 API 标准价估算的，订阅用户实际支出不同。
   - 告诉用户还可以换时间维度，例如“生成我的 vibe 本月报告”。

6. 昵称（传播位，只问一次）
   - 先运行 `python3 <skill>/scripts/wrapped.py doctor`，看“海报昵称”一行：已有就不要再问。
   - 没有的话，出完图后问一次：“想在海报左上角加个昵称吗？告诉我名字就行，不要也可以。”
   - 用户给了就运行 `python3 <skill>/scripts/wrapped.py profile --nickname "<名字>"`，然后重新 render。昵称只保存在本机 `~/.vibe-wrapped/`，之后每次自动使用。
   - 用户说不要，就不再问；要清除用 `profile --clear`。

## 禁止事项
- 不要把日志内容、原话、路径发到任何网络服务。
- 不要读取认证文件（`auth.json`、`.credentials.json` 等），脚本也不会读。
- 不要编造脚本没有给出的数字。
