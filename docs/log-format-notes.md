# 日志格式核对结论（2026-10-14，基于本机真实日志）

## Claude Code（~/.claude/projects/<cwd>/<sessionId>.jsonl）
- 行内 `type`：user / assistant 之外还有 attachment、queue-operation、last-prompt、custom-title、agent-name、file-history-snapshot、system、cost-state、mode 等，全部忽略并计数。
- 人打的字：`type=user`、非 `isMeta`、`origin.kind=="human"`（或无 origin）、`message.content` 为字符串，或为只含 text 块的数组（带图片时是 image+text）。含 `tool_result` 的整条不算。
- 注入文本需剔除：`<command-name>`、`<local-command…>`、`<system-reminder>`、`<task-notification>`、`Caveat:`、续接摘要等。
- 打断：用户行 text 以 `[Request interrupted by user` 开头。
- usage 在每个 assistant 行的 `message.usage`；同一 `message.id`+`requestId` 的多行共享 usage，取 output 最大的一行去重。
- 工具文件路径字段：`input.file_path`（Edit/Write/MultiEdit），`input.notebook_path`（NotebookEdit）。

## Codex（~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl + archived_sessions/）
- **三代格式并存**：
  1. 新：`event_msg.item_completed`，`item.type` 为 `UserMessage` / `AgentMessage`（content[].text）。
  2. 中：`response_item` role=user / assistant。
  3. 老：同上，且用户消息混有 IDE 上下文、AGENTS.md、`<environment_context>`、`<turn_aborted>`、`<recommended_plugins>` 等注入。
- 本机日志里**没有** `event_msg.user_message`（PRD 假设不成立），适配器保留它作为次选来源。
- IDE 注入的真话在 `## My request for Codex:` 之后。
- token：`event_msg.token_count`（info 可能为 null，且会重复发射同一累计值 → 用累计 total 差分去重）；新版另有顶层 `token_usage_record`（数值与 token_count 重复，只在没有 token_count 时使用）。`cached_input_tokens` 是 `input_tokens` 的一部分。
- 模型：`turn_context.payload.model`，每个 usage 事件取当时最近的一个。
- 子代理：`session_meta.payload.source = {"subagent": …}`。
- 打断：`event_msg.turn_aborted`（同时有一条 `<turn_aborted>` 注入的 user message，已剔除，不重复计）。
- 改文件：`response_item.custom_tool_call` name=`apply_patch`，补丁文本里 `*** Add/Update/Delete File: <path>`；命令执行为 `function_call` name=`exec_command`，`arguments` 是 JSON 字符串（字段 `cmd`）。
- `sessions/` 与 `archived_sessions/` 在本机无同名文件；若有，以 `sessions/` 为准。
