# vibe-wrapped · Vibe Coding 人格年报

> 程序员版 Spotify Wrapped。读你本机的 **Claude Code** 和 **Codex** 会话日志，算出你这一年怎么跟 AI 写代码，给你一个人格类型和一张能直接发的海报。
> Local-only Spotify-Wrapped for vibe coders. Reads your Claude Code + Codex logs, gives you a persona and a shareable poster. Nothing leaves your machine.

## 你会得到什么

| 文件 | 用途 |
|---|---|
| `poster-3x4.png` | 1080×1440（2× 清晰度），小红书 / 朋友圈 / X |
| `poster-9x16.png` | 1080×1920，故事 / 全屏 |
| `poster-*.html` | 同内容的网页版，可直接在浏览器打开 |
| `share.txt` | 可复制的小红书文案、X 文案、**让你的 AI 当面吐槽你的提示词** |
| `metrics.json` / `persona.json` | 全部数字与来源，海报上每个数字都能在这里查到 |

8 种人格（夜猫 × 脾气 × 放手）：深夜甩锅型、熬夜暴躁监工、午夜甩手掌柜、深夜温柔调教型、白天甩锅型、暴躁监工型、甩手掌柜型、温柔调教型；外加和 AI 的“关系诊断”与成就徽章。

## 安装

```bash
git clone https://github.com/yaohongan/vibe-wrapped
cd vibe-wrapped && bash install.sh       # 装到所有平台
bash install.sh --claude | --codex       # 只装一个
```

安装用**复制**（Codex 会跳过软链）：`~/.claude/skills/`、`~/.agents/skills/`、`~/.codex/skills/`。装完重启。

- Claude Code：直接说“生成我的 vibe 年报”
- Codex：`/skills` 或 `$vibe-wrapped`
- 旧版 Codex 看不到 skill：在 `~/.codex/config.toml` 加 `[features] skills = true`

不装 Skill 也能用：

```bash
python3 scripts/wrapped.py all            # 统计 + 出图（使用预设短评）
python3 scripts/wrapped.py doctor         # 检查环境
```

## 常用参数

```
--year 2026 | --since 2026-01-01 --until 2026-12-31 | --all
--tz Asia/Shanghai          时区（默认系统时区）
--platform claude_code|codex
--show-projects             显示真实项目名/文件名（默认匿名：项目 A/B/C，*.tsx）
--no-quotes | --show-quotes 原话：不显示 / 关闭脱敏（默认脱敏）
--nickname NAME             海报右上角昵称
--size 1080x1440|1080x1920
--html-only                 只输出 HTML
```

## 设计原则

1. **确定性**：所有数字和人格由 Python 脚本算，同样的输入同样的输出；AI 只写最后一句 ≤40 字的毒舌短评。
2. **全本地**：无任何网络请求（有测试覆盖）；只读会话目录，不读 `auth.json` 等认证文件。
3. **隐私默认保守**：项目名/文件名默认匿名；原话默认脱敏（邮箱/URL/路径/密钥/长数字）；给 AI 看的 `persona.json` 只含聚合数字。
4. **只依赖标准库**：Python ≥3.9。渲染用本机 Chrome/Edge/Chromium headless，其次 Playwright，最后只输出 HTML。

## 口径说明

- 窗口默认今年 1 月 1 日至今；子代理（subagent）消息不计入你的行为指标，但计入花费。
- 花费按 `data/pricing.json` 的 **API 标准价**估算，订阅用户实际支出不同；价格表更新日期见文件头。
- Codex 日志有多代格式并存，适配器自动兼容；老版本没有 token 数据的会话不估算成本。
- 单条用户消息按 500 字封顶计入平均字数，避免粘贴整篇文档把均值拉歪。
- 日志是各 CLI 的内部格式，随版本会变；坏行占比 >5% 时会提示“日志格式可能更新了”。

## 开发

```bash
python3 -m unittest discover -s tests
```

MIT License
