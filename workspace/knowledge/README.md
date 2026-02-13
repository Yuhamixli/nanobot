# Knowledge Base 知识库

将**制度、规范、政策**等文档放在此目录下。

## 目录结构（长期 / 短期）

| 目录 | 用途 | 清理策略 |
|------|------|----------|
| **长期/** | 制度、手册、政策、重要文档 | 不自动清理 |
| **短期/** | 爬取内容、临时资料、web 缓存 | 按 TTL 定期清理（默认 7 天） |

> **路径说明**：nanobot 默认工作区是 `~/.nanobot/workspace`，因此**实际放文档的目录**是 **`~/.nanobot/workspace/knowledge`**（如 Windows：`C:\Users\你的用户名\.nanobot\workspace\knowledge`），不是项目里的 `workspace\knowledge`。**不要**把文档堆在 workspace 根目录，也不要放进 `knowledge_db`（那是向量库，程序自动用）。首次运行 `nanobot knowledge ingest` 若该目录不存在会自动创建并提示路径。

**推荐**：在 `knowledge/长期/` 下按主题建子文件夹，例如 `knowledge/长期/财务制度`、`knowledge/长期/集团发文`。执行 `nanobot knowledge ingest` 会递归导入整个 knowledge；若只导入某一类，可执行 `nanobot knowledge ingest knowledge/长期`。

## 支持格式

- TXT、MD（纯文本 / Markdown）
- PDF
- Word（.docx）
- Excel（.xlsx）

## 你需要做的（使用步骤）

1. **放置文件**：把要纳入知识库的文档复制到本目录 `workspace/knowledge/`（或你配置的 workspace 下的 `knowledge` 文件夹）。
2. **导入知识库**（二选一）：
   - **命令行**：在项目根目录执行  
     `nanobot knowledge ingest`  
     （默认导入 `knowledge` 目录；也可指定路径，如 `nanobot knowledge ingest knowledge/制度`）
   - **商网/对话**：直接对 agent 说「把 knowledge 目录导入知识库」「导入知识库」或「这个也放你的库里」，agent 会调用 `knowledge_ingest` 工具。若文件已在 knowledge 目录，agent 会先执行导入再确认「已导入」。
   - **商网自动保存**：在商网中发送的文档（PDF、Word、Excel、TXT、MD）会**自动保存**到 `knowledge/长期/来自商网/`，随后对 agent 说「导入知识库」即可完成导入。
3. **提问**：在商网或任意通道向 agent 提问，例如「差旅报销标准是什么？」。Agent 会先调用 `knowledge_search` 检索知识库，再根据检索结果回答。

## 首次使用前

- 安装 RAG 依赖：`pip install nanobot-ai[rag]`（或从源码 `pip install -e ".[rag]"`）
- 若未运行过 `nanobot onboard`，请先运行一次以创建 workspace 和本目录。
- **首次 ingest 会下载 BGE 中文向量模型**（约数百 MB）。程序已默认使用国内镜像，若仍超时请检查网络；国外用户可设 `HF_ENDPOINT=https://huggingface.co`。

## 商网群聊历史 → 学习管理员回复口吻

当商网 channel 启用且配置了 `adminNames` / `adminIds` 时，群聊消息会自动记录到 `workspace/chat_history/shangwang/`。

**导出与导入**：
```bash
# 方案二：实时记录（gateway 运行即自动记录，无需配置 admin 也可先存）
nanobot chat-history list            # 查看已记录的会话 ID（team-xxx 等）
nanobot chat-history fetch-chat      # 方案四：从当前窗口采集历史（需先切换到目标群）
nanobot chat-history re-role         # 配置 admin 后重新标记 role
nanobot chat-history diagnose        # 诊断为何无法导出
nanobot chat-history export          # 导出全部
nanobot chat-history export --chat-id team-xxx   # 只导出指定群
nanobot chat-history export-ingest   # 导出并 ingest 到知识库
```
- **方案二**：gateway 启动时即开始记录，无需 admin 也可先存（后续可 re-role）
- **方案四**：fetch-chat 从 Vue store 采集当前窗口历史，与实时记录自动去重
- 导出结果会标注每条示例的来源群（chat_id）

**配置**：在 `~/.nanobot/config.json` 的 `channels.shangwang` 中：
- `chatHistoryEnabled`: true（默认）
- `adminNames`: ["张三", "李四"]  # 管理员昵称
- `adminIds`: ["accid1"]  # 或管理员账号 ID（二选一或同时配置）

**查询 ID**：`nanobot channels shangwang my-id` 查自己的 ID；`nanobot channels shangwang current-session` 查当前聊天窗口的对方 ID（私聊时）。

导出后的 markdown 会以「客户」「管理员」格式组织，agent 检索时会参考这些示例的回复口吻。

## 网络搜索结果缓存（Web Cache）

当 agent 使用 `web_search` 或 `web_fetch` 时，检索结果会自动存入 `knowledge/短期/_cache_web/` 并做向量 ingest，供 `knowledge_search` 检索。重复问题可更快从缓存中回答，无需再次调用网络。

- 缓存目录：`workspace/knowledge/短期/_cache_web/`（程序自动创建）
- 清理周期：**每周**自动清空（由 gateway 的 heartbeat 触发）
- 配置：`tools.knowledge.webCacheEnabled` 设为 `false` 可关闭此功能

## 短期知识清理

`knowledge/短期/` 下的文件（除 `_cache_web` 外）按 `shortTermRetentionDays` 配置的保留天数自动清理。超期文件及其向量会被删除。默认 7 天。

## 配置（可选）

在 `~/.nanobot/config.json` 的 `tools.knowledge` 中可调整：

- `chunkSize`：分块大小（约 token 数，默认 512）
- `chunkOverlap`：块重叠（默认 200）
- `topK`：检索返回条数（默认 5）
- `webCacheEnabled`：网络搜索缓存（默认 true）
- `shortTermRetentionDays`：短期知识保留天数（默认 7）
- `enabled`：设为 `false` 可关闭知识库工具
