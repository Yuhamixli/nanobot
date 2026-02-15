# nanobot 开发路线图 (TODO)


~~有什么办法能监控所有商网的聊天记录和历史记录，用于训练机器人？比如一个群里面，有客户和运维管理论人，我想把这两类人的问题和答复分别提取出来，学习运维管理员的答复。想说说计划，再来实施。~~ **已实现方案二**：实时监控 + 本地持久化，配置 adminNames/adminIds 区分客户 vs 管理员，`nanobot chat-history export-ingest` 导出并 ingest。


> 更新时间: 2026-02-15

## 已完成

### Phase 1: 基础架构
- [x] nanobot 核心 agent loop
- [x] Telegram 通道集成
- [x] WhatsApp 通道集成
- [x] 企业微信通道集成
- [x] 多轮对话支持
- [x] Web 搜索工具
- [x] 文件读写工具
- [x] Shell 执行工具
- [x] 浏览器自动化工具

### Phase 2: 商网办公集成
- [x] 深度分析 Avic.exe 架构（Electron + NIM SDK）
- [x] shangwang-bridge CDP 模式实现
- [x] NIM SDK hook 注入（收消息）
- [x] NIM sendText 调用（发消息）
- [x] 回显过滤（flow/account/text 三层）
- [x] 消息去重（时间窗口 dedup）
- [x] nanobot ShangwangChannel 通道
- [x] 端到端通信验证：收消息 → nanobot 处理 → 回复到正确会话

---

## 进行中 / 待完成

### Phase 2.5: 代码审计整改（2026-02-15）🧪

#### P0（立即修复，保证正确性）
- [ ] 修复 `AgentLoop.process_direct`：`session_key` 参数目前未生效，导致 CLI 会话串线
- [ ] 修复 `gateway` 心跳维护分支中的 `logger` 未定义问题（避免定时清理时崩溃）
- [ ] 修复 `knowledge_get_document` 的 Chroma `get()` 结果解析（当前索引结构与实际返回不一致）
- [ ] 修复 `browser_automation` 的 `extract` 逻辑（`textContent/innerText/innerHTML` 读取方式不正确）

#### P1（本周内，降低维护成本）
- [ ] 抽取统一的 LLM + tool 调度循环，合并 `AgentLoop` 主流程、system 流程、`SubagentManager` 重复代码
- [ ] 抽取 CLI 公共函数：Provider 配置校验、商网 bridge URL 规范化（目前多处重复）
- [ ] 抽取 `ChatHistoryRecorder` 公共 JSONL 读取函数，统一异常处理与数据清洗
- [ ] 统一文件名清洗函数（`safe_filename/_sanitize_filename/_safe_filename`）避免规则漂移

#### P2（治理项）
- [ ] 统一版本号来源（`pyproject.toml` 与 `nanobot/__init__.py` 当前不一致）
- [ ] 固化测试环境并启用 async 测试必跑（当前有 async case 被 skip）
- [ ] 清理仓库已提交的 `__pycache__/*.pyc` 构建产物并加入发布前检查

### Phase 3: 角色 Prompt 与安全 🔒
- [x] 起草航空工业财务智能办公助手 system prompt（中航小诺）：见 `workspace/AGENTS.md`，角色为司库管理 AI 智能员工，融合技术/业务/财务/税务，覆盖穿透监管、资金集中与结算等，回答专业准确精简，不透露实现与产品信息，开发者程昱涵（航空工业财务公司）
- [ ] 用户测试并调优 prompt（自然度、准确度、安全性）
- [ ] Prompt 注入攻防测试（DAN / 越狱 / prompt leak）
- [ ] 多角色支持（不同部门/场景切换不同 persona）

### Phase 4: 本地知识库 (RAG) 📚
- [x] 选型与 PoC（ChromaDB + BGE-small-zh 向量检索，见下方方案对比）
- [x] 文档导入管道（PDF/Word/Excel/TXT/MD → 分块 → 向量化 → ChromaDB）
- [x] 检索增强生成（RAG）集成到 agent loop（knowledge_search / knowledge_ingest 工具）
- [x] 知识库管理：CLI `nanobot knowledge ingest`、`nanobot knowledge status`
- [ ] **后续接入 LightRAG**（混合图谱+向量，多跳推理、降幻觉、省 token，见下方技术栈）
- [ ] 财务领域 embedding 优化（中文 + 专业术语）

#### 用户需做（商网提问 + 知识库回复）
1. 安装 RAG 依赖：`pip install nanobot-ai[rag]`
2. 将制度/政策文档放入 **workspace 下的 `knowledge` 目录**（如 `~/.nanobot/workspace/knowledge/`）
3. 执行导入：`nanobot knowledge ingest`（或让 agent 执行 knowledge_ingest，path 填 `knowledge`）
4. 在商网或任意通道提问，agent 会自动检索知识库并回复

详见 `workspace/knowledge/README.md`。

#### 知识库方案对比

| 方案 | 适用场景 | 优点 | 缺点 | 推荐度 |
|------|----------|------|------|--------|
| **LightRAG + ChromaDB** | 混合图谱+向量 | 多跳推理、低幻觉、轻量 | 需实体抽取管道 | ⭐⭐⭐⭐⭐ |
| **LlamaIndex + ChromaDB** | 纯向量 RAG | 开箱即用、150+ 数据连接器 | 复杂关系推理弱 | ⭐⭐⭐⭐ |
| **LangChain + Qdrant** | 编排为主 | 灵活度高、工具链丰富 | 框架偏重 | ⭐⭐⭐ |

**规划**：当前为纯向量检索（ChromaDB + BGE），**后续将切换/接入 LightRAG**。采用 LightRAG 的原因：
1. 财务场景需要多跳推理（如：某子公司 → 所属板块 → 适用政策）
2. 减少幻觉（6% reduction vs 纯向量），财务数据零容错
3. 节省 token 消耗（80% reduction），适合高频使用
4. 本地运行，数据不出网，满足涉密要求

**目标技术栈（LightRAG）**:
```
文档 → 分块(512 token/200 overlap) → Embedding(BGE-small-zh)
                                          ↓
                                    ChromaDB(向量存储)
                                    LightRAG(知识图谱)
                                          ↓
                                    RAG 检索 → nanobot agent
```

### Phase 5: 工具调用扩展 🔧

#### 5.1 已有工具
- `read_file` / `write_file` / `edit_file` — 文件操作
- `exec` — 命令执行
- `web_search` / `web_fetch` — 网页搜索与抓取
- `browser_automation` — 浏览器自动化（Playwright）
- `message` — 消息推送（各通道）
- `spawn` — 子 agent 异步执行

#### 5.2 工具清单

| 工具名 | 功能 | 状态 | 说明 |
|--------|------|------|------|
| `knowledge_search` | 本地知识库检索 | ✅ 已实现 | RAG 核心，检索财务文档/制度 |
| `knowledge_ingest` | 文档导入知识库 | ✅ 已实现 | 支持 PDF/Word/Excel/TXT |
| `knowledge_list` | 列出已导入文档 | ✅ 已实现 | 辅助检索、避免重复导入 |
| `calculator` | 精确数值计算 | 待开发 | 避免 LLM 计算错误，支持财务公式 |
| `excel_tool` | Excel 读写与分析 | 待开发 | openpyxl/pandas，读取报表数据 |
| `pdf_extract` | PDF 解析 | 待开发 | 提取 PDF 中的表格和文本 |
| `calendar` | 日程管理 | 待开发 | 会议提醒、报表截止日期 |
| `email_draft` | 邮件草稿生成 | 待开发 | 生成格式化的财务邮件 |
| `template_fill` | 模板填充 | 待开发 | 自动填充财务报表模板 |
| `ocr` | 图片文字识别 | 待开发 | 识别扫描件、票据（image_understander skill 已有 OCR） |

#### 5.3 工具开发路径

```
P0 ✅ 已完成:  knowledge_search + knowledge_ingest + knowledge_list
P1 (下一步):  calculator + excel_tool + pdf_extract
P2 (2周后):   calendar + email_draft + template_fill
P3 (后续):    ocr 独立工具（或复用 image_understander skill）
```

### Phase 6: 生产化 🚀
- [ ] 商网 bridge 开机自启（Windows 服务 / 计划任务）
- [ ] nanobot gateway 守护进程
- [ ] 日志收集与监控
- [ ] 对话审计日志（合规留痕）
- [ ] 多用户会话隔离
- [ ] 性能优化（长对话 token 管理）

### Phase 7: 业务需求
- [ ] 涉密信息查询
- [ ] 公文格式skill
- [ ] 知识审计skill
---

## 备注

- 所有数据本地处理，不出网（满足涉密要求）
- LLM 通过 OpenRouter 调用，走 HTTPS，无明文传输风险
- 财务敏感数据不应直接发送给 LLM，RAG 检索结果需脱敏处理
