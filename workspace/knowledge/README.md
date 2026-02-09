# Knowledge Base 知识库

将**制度、规范、政策**等文档放在此目录下。

> **路径说明**：nanobot 默认工作区是 `~/.nanobot/workspace`，因此**实际放文档的目录**是 **`~/.nanobot/workspace/knowledge`**（如 Windows：`C:\Users\你的用户名\.nanobot\workspace\knowledge`），不是项目里的 `workspace\knowledge`。**不要**把文档堆在 workspace 根目录，也不要放进 `knowledge_db`（那是向量库，程序自动用）。首次运行 `nanobot knowledge ingest` 若该目录不存在会自动创建并提示路径。

**推荐**：在 `knowledge` 下按主题建子文件夹，例如 `knowledge/财务制度`、`knowledge/集团发文`。执行 `nanobot knowledge ingest` 会递归导入整个 knowledge；若只导入某一类，可执行 `nanobot knowledge ingest knowledge/财务制度`。

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
   - **商网/对话**：直接对 agent 说「把 knowledge 目录导入知识库」或「导入知识库」，agent 会调用 `knowledge_ingest` 工具。
3. **提问**：在商网或任意通道向 agent 提问，例如「差旅报销标准是什么？」。Agent 会先调用 `knowledge_search` 检索知识库，再根据检索结果回答。

## 首次使用前

- 安装 RAG 依赖：`pip install nanobot-ai[rag]`（或从源码 `pip install -e ".[rag]"`）
- 若未运行过 `nanobot onboard`，请先运行一次以创建 workspace 和本目录。
- **首次 ingest 会下载 BGE 中文向量模型**（约数百 MB）。程序已默认使用国内镜像，若仍超时请检查网络；国外用户可设 `HF_ENDPOINT=https://huggingface.co`。

## 配置（可选）

在 `~/.nanobot/config.json` 的 `tools.knowledge` 中可调整：

- `chunkSize`：分块大小（约 token 数，默认 512）
- `chunkOverlap`：块重叠（默认 200）
- `topK`：检索返回条数（默认 5）
- `enabled`：设为 `false` 可关闭知识库工具
