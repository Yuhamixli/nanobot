<div align="center">
  <img src="nanobot_logo.png" alt="中航小诺" width="500">
  <h1>中航小诺，智能体协同网络管家</h1>
  <p>
    <a href="https://pypi.org/project/nanobot-ai/"><img src="https://img.shields.io/pypi/v/nanobot-ai" alt="PyPI"></a>
    <a href="https://pepy.tech/project/nanobot-ai"></a>
    <img src="https://img.shields.io/badge/python-≥3.11-blue" alt="Python">
    <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
    
  </p>
</div>

🐈 **nanobot** is an **ultra-lightweight** personal AI assistant inspired by [Clawdbot](https://github.com/openclaw/openclaw) 

⚡️ Delivers core agent functionality in roughly **~7,000+ Python LOC** (2026-02 snapshot), still with a compact and readable architecture.

## 📢 News

- **2026-02-01** 🎉 nanobot launched! Welcome to try 🐈 nanobot!

## Key Features of nanobot:

🪶 **Ultra-Lightweight**: Core capabilities in ~7k Python lines, focused on readable architecture and maintainable modules.

🔬 **Research-Ready**: Clean, readable code that's easy to understand, modify, and extend for research.

⚡️ **Lightning Fast**: Minimal footprint means faster startup, lower resource usage, and quicker iterations.

💎 **Easy-to-Use**: One-click to depoly and you're ready to go.

## 🏗️ Architecture

<p align="center">
  <img src="nanobot_arch.png" alt="nanobot architecture" width="800">
</p>

## 🔍 Code Audit (2026-02-15)

本次审计覆盖 `nanobot/`、`shangwang-bridge/`、`bridge/`，重点检查了代码冗余、实现逻辑一致性、可维护性与测试有效性。

### 核心执行链路（当前实现）

1. `nanobot cli` 启动后，创建 `MessageBus`、`AgentLoop`、`ChannelManager`、`CronService`、`HeartbeatService`。
2. 渠道消息统一进入 `InboundMessage`，由 `AgentLoop` 组装上下文并调用 LLM。
3. Tool Calling 通过 `ToolRegistry` 执行（文件、命令、Web、RAG、消息、子 agent）。
4. 输出统一为 `OutboundMessage`，由 `ChannelManager` 分发到 Telegram/WhatsApp/商网/WeCom。
5. 商网链路通过 `shangwang-bridge`（CDP + NIM hook）转发消息与附件。

### 主要问题（按优先级）

| 优先级 | 类型 | 发现 | 建议 |
|---|---|---|---|
| P0 | 逻辑缺陷 | `AgentLoop.process_direct` 的 `session_key` 参数未生效，所有 CLI 直连对话写入同一会话 | 在 `process_direct` 中按 `session_key` 拆分 `channel/chat_id` 或直接显式传递会话键 |
| P0 | 逻辑缺陷 | `knowledge_get_document` 读取 Chroma `get()` 结果时按嵌套结构访问，可能导致文档 chunk 读取异常 | 统一按 Chroma `get()` 的扁平返回结构解析，并补单元测试 |
| P0 | 逻辑缺陷 | `browser_automation` 的 `extract` 对 `textContent/innerText/innerHTML` 使用 `get_attribute`，结果可能为空 | 改为 `inner_text()/text_content()/evaluate()` 读取 DOM 属性 |
| P0 | 稳定性 | `gateway` 心跳清理分支使用 `logger` 但文件未导入，触发时会抛 `NameError` | 引入统一 logger 或改为 `console/logging` |
| P1 | 冗余 | 主 agent、system 消息处理、subagent 各自实现一套近似 LLM-tool 循环 | 抽取统一 `run_llm_with_tools()` 执行器，减少三处重复 |
| P1 | 冗余 | CLI 中 API Key 检查与商网 bridge URL 规范化逻辑重复 | 抽成 `_validate_provider_config()` 与 `_normalize_ws_url()` 工具函数 |
| P1 | 冗余 | `ChatHistoryRecorder` 多处重复 JSONL 读取解析 | 抽 `_load_rows(path)`，统一异常与空行处理 |
| P2 | 一致性 | 包版本号存在双源：`pyproject.toml` 与 `nanobot/__init__.py` 不一致 | 统一单一版本源（建议来自 `pyproject`） |
| P2 | 测试 | 当前 async 测试被跳过（缺少 `pytest-asyncio` 实际生效环境） | CI 固化 dev 依赖并将 async 测试改为必跑 |

### 审计建议（实施顺序）

1. 先修 P0（逻辑正确性）并补最小回归测试。
2. 再做 P1（重复实现收敛），降低后续功能迭代成本。
3. 最后处理 P2（版本与测试治理），避免发布与运维偏差。

## ✨ Features

<table align="center">
  <tr align="center">
    <th><p align="center">📈 24/7 Real-Time Market Analysis</p></th>
    <th><p align="center">🚀 Full-Stack Software Engineer</p></th>
    <th><p align="center">📅 Smart Daily Routine Manager</p></th>
    <th><p align="center">📚 Personal Knowledge Assistant</p></th>
  </tr>
  <tr>
    <td align="center"><p align="center"><img src="case/search.gif" width="180" height="400"></p></td>
    <td align="center"><p align="center"><img src="case/code.gif" width="180" height="400"></p></td>
    <td align="center"><p align="center"><img src="case/scedule.gif" width="180" height="400"></p></td>
    <td align="center"><p align="center"><img src="case/memory.gif" width="180" height="400"></p></td>
  </tr>
  <tr>
    <td align="center">Discovery • Insights • Trends</td>
    <td align="center">Develop • Deploy • Scale</td>
    <td align="center">Schedule • Automate • Organize</td>
    <td align="center">Learn • Memory • Reasoning</td>
  </tr>
</table>

## 📦 Install

**Install from source** (latest features, recommended for development)

```bash
git clone https://github.com/HKUDS/nanobot.git
cd nanobot
pip install -e .
```

**Install with [uv](https://github.com/astral-sh/uv)** (stable, fast)

```bash
uv tool install nanobot-ai
```

**Install from PyPI** (stable)

```bash
pip install nanobot-ai
```

## 🚀 Quick Start

> [!TIP]
> Set your API key in `~/.nanobot/config.json`.
> Get API keys: [OpenRouter](https://openrouter.ai/keys) (LLM) · [Brave Search](https://brave.com/search/api/) (optional, for web search)
> 模型在 `agents.defaults.model` 配置，推荐：`anthropic/claude-opus-4-5`、`openai/gpt-4o`；省成本可用 `minimax/minimax-m2`，`moonshotai/kimi-k2.5`。

**1. Initialize**

```bash
nanobot onboard
```

**2. Configure** (`~/.nanobot/config.json`)

```json
{
  "providers": {
    "openrouter": {
      "apiKey": "sk-or-v1-xxx"
    }
  },
  "agents": {
    "defaults": {
      "model": "anthropic/claude-opus-4-5"
    }
  },
  "tools": {
    "web": {
      "search": {
        "apiKey": "BSA-xxx"
      }
    }
  }
}
```


**3. Chat**

```bash
nanobot agent -m "What is 2+2?"
```

That's it! You have a working AI assistant in 2 minutes.

> **项目模式**：将 `config.example.json` 复制为 `~/.nanobot/config.json`，workspace 已指向 `c:/Projects/nanobot/workspace`，知识库、记忆、技能随项目版本控制与部署。

## 🌐 RPA / 浏览器自动化

通过 **browser_automation** 工具，可以让 agent 驱动浏览器：打开外网页面、登录、填表、点击、提取内容，适合与需要在前端操作的平台（如企业商网）对接。

**安装可选依赖**

```bash
pip install playwright
playwright install chromium
```

或安装 nanobot 的 RPA 可选组：`pip install "nanobot-ai[rpa]"`，再执行 `playwright install chromium`。

**使用方式**

直接对 agent 说人话即可，例如：

- 「打开 https://example.com 并提取页面标题」
- 「打开某商网登录页，在用户名框填 xxx、密码框填 xxx，点登录，然后提取待办列表」

Agent 会调用 `browser_automation`，按步骤执行：`navigate` → `fill` / `click` → `extract`。若页面选择器复杂，可在 AGENTS.md 或对话中说明页面结构（如「登录按钮的 id 是 submit」）以便更稳确定位。

## 🖥️ Local Models (vLLM)

Run nanobot with your own local models using vLLM or any OpenAI-compatible server.

**1. Start your vLLM server**

```bash
vllm serve meta-llama/Llama-3.1-8B-Instruct --port 8000
```

**2. Configure** (`~/.nanobot/config.json`)

```json
{
  "providers": {
    "vllm": {
      "apiKey": "dummy",
      "apiBase": "http://localhost:8000/v1"
    }
  },
  "agents": {
    "defaults": {
      "model": "meta-llama/Llama-3.1-8B-Instruct"
    }
  }
}
```

**3. Chat**

```bash
nanobot agent -m "Hello from my local LLM!"
```

> [!TIP]
> The `apiKey` can be any non-empty string for local servers that don't require authentication.

## 💬 Chat Apps

Talk to your nanobot through Telegram, WhatsApp, or 企业微信 (WeCom) — anytime, anywhere.

| Channel | Setup |
|---------|-------|
| **商网办公 (AVIC)** | CDP Bridge（需 Windows） |
| **Telegram** | Easy (just a token) |
| **WhatsApp** | Medium (scan QR) |
| **企业微信 (WeCom)** | 企业应用（发消息） |


<details>
<summary><b>商网办公 (Shangwang / AVIC Office)</b></summary>

通过 **Chrome DevTools Protocol (CDP)** 连接已登录的商网办公 Avic.exe（Electron 应用），直接 hook 内嵌的网易云信 NIM SDK，实现消息的实时收发。无需爬虫或 OCR，稳定可靠。

**前提条件**
- Windows 系统，商网办公 (Avic.exe) 已安装
- 中国境内网络（商网不支持海外访问）

**1. 启动 Avic.exe（带调试端口）**

修改桌面快捷方式的「目标」，或在 PowerShell 中直接运行：

```powershell
& "C:\Program Files (x86)\AVIC Office\Avic.exe" --remote-debugging-port=9222
```

**2. 手动登录商网办公**，进入聊天界面。

**3. 启动 Bridge**

```bash
cd shangwang-bridge
pip install -r requirements.txt
python main.py
```

**4. 配置 nanobot** (`~/.nanobot/config.json`)

```json
{
  "channels": {
    "shangwang": {
      "enabled": true,
      "bridgeUrl": "ws://localhost:3010",
      "mentionNames": ["程昱涵"],
      "groupReplyMaxLength": 200
    }
  }
}
```

- `mentionNames`: 群聊中仅回复 @提及 了这些昵称的消息，私聊不受影响；空数组则回复所有群消息
- `groupReplyMaxLength`: 群聊回复最大字数（默认 200），超出自动截断

**5. 运行**

```bash
nanobot gateway
```

> 详细文档见 [shangwang-bridge/README.md](./shangwang-bridge/README.md)

</details>

<details>
<summary><b>本地知识库 (RAG)</b></summary>

商网（或任意通道）提问时，agent 可检索本地知识库并基于制度/政策文档回复。

**1. 安装 RAG 依赖**

```bash
pip install nanobot-ai[rag]
```

**2. 放置文档**  
将制度、规范、政策等文件放入 **workspace 下的 `knowledge` 目录**。项目模式：`c:/Projects/nanobot/workspace/knowledge/`；默认：`~/.nanobot/workspace/knowledge/`。支持：TXT、MD、PDF、Word(.docx)、Excel(.xlsx)。

**3. 导入知识库**

```bash
nanobot knowledge ingest
```

或对 agent 说「导入 knowledge 目录到知识库」，agent 会调用 `knowledge_ingest`。

**4. 提问**  
在商网或 CLI 直接提问，例如「差旅报销标准是什么？」。Agent 会先 `knowledge_search` 检索，再结合结果回答。

可选配置见 `~/.nanobot/config.json` 的 `tools.knowledge`（chunkSize、topK、enabled、webCacheEnabled 等）。  
**网络搜索缓存**：`web_search` / `web_fetch` 结果会自动存入 `knowledge/短期/_cache_web/` 并 ingest，重复问题可更快回答；每周自动清空。详见 [workspace/knowledge/README.md](./workspace/knowledge/README.md)。

</details>
<details>
<summary><b>Telegram</b> </summary>

**1. Create a bot**
- Open Telegram, search `@BotFather`
- Send `/newbot`, follow prompts
- Copy the token

**2. Configure**

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "YOUR_BOT_TOKEN",
      "allowFrom": ["YOUR_USER_ID"]
    }
  }
}
```

> Get your user ID from `@userinfobot` on Telegram.

**3. Run**

```bash
nanobot gateway
```

</details>

<details>
<summary><b>WhatsApp</b></summary>

Requires **Node.js ≥18**.

**1. Link device**

```bash
nanobot channels login
# Scan QR with WhatsApp → Settings → Linked Devices
```

**2. Configure**

```json
{
  "channels": {
    "whatsapp": {
      "enabled": true,
      "allowFrom": ["+1234567890"]
    }
  }
}
```

**3. Run** (two terminals)

```bash
# Terminal 1
nanobot channels login

# Terminal 2
nanobot gateway
```

</details>

<details>
<summary><b>企业微信 (WeCom)</b></summary>

通过企业微信「自建应用」向成员发送消息（当前支持**发送**；接收用户消息需在企业微信后台配置回调，后续版本可支持）。

**1. 创建自建应用**

- 登录 [企业微信管理后台](https://work.weixin.qq.com/wework_admin/loginpage_wx)
- 「应用管理」→「自建」→ 创建应用，记录 **AgentId**、**Secret**
- 「我的企业」→「企业信息」→ 记录 **企业 ID (corp_id)**

**2. 配置**

```json
{
  "channels": {
    "wecom": {
      "enabled": true,
      "corpId": "wwxxxxxxxx",
      "agentId": 1000002,
      "secret": "xxxxxxxx",
      "allowFrom": []
    }
  }
}
```

- `allowFrom` 为空表示允许所有成员；可填成员 UserID 限制接收范围。
- 发往某成员时，cron/脚本里 `deliver.to` 填该成员的 **UserID**；发全员可填 `@all`。

**3. 运行**

```bash
nanobot gateway
```

</details>




## ⚙️ Configuration

Config file: `~/.nanobot/config.json`

### Web Search（网页搜索）

Agent 的「搜索互联网」能力依赖 **Brave Search API**。若未配置 `tools.web.search.apiKey`，`web_search` 会报错，agent 会退而用 `web_fetch`、浏览器自动化等方式，效果差（如你看到的「无法直接获取金融新闻」）。

**配置步骤**：在 `~/.nanobot/config.json` 的 `tools.web.search` 中填入 `apiKey`，申请地址：[Brave Search API](https://brave.com/search/api/)（免费档可用）。

```json
"tools": {
  "web": {
    "search": {
      "apiKey": "BSA-你的Key",
      "maxResults": 5,
      "proxy": "http://127.0.0.1:7890"
    }
  }
}
```

- **国内网络**：Brave API（api.search.brave.com）可能被限速或超时。若网页搜索一直失败，可（二选一）：在 `tools.web.search` 里加上 `proxy`（如本地代理 `http://127.0.0.1:7890`）；或先设置环境变量 `HTTPS_PROXY` 再启动 gateway（如 PowerShell：`$env:HTTPS_PROXY="http://127.0.0.1:7890"; nanobot gateway`）。改配置或环境后需**重启 gateway**。
- **若使用商网/Telegram 等 gateway**：修改 `config.json` 后必须**重启 nanobot gateway** 才会生效（gateway 只在启动时读一次配置）。

### Providers

> [!NOTE]
> Groq provides free voice transcription via Whisper. If configured, Telegram voice messages will be automatically transcribed.

| Provider | Purpose | Get API Key |
|----------|---------|-------------|
| `openrouter` | LLM (recommended, access to all models) | [openrouter.ai](https://openrouter.ai) |
| `anthropic` | LLM (Claude direct) | [console.anthropic.com](https://console.anthropic.com) |
| `openai` | LLM (GPT direct) | [platform.openai.com](https://platform.openai.com) |
| `groq` | LLM + **Voice transcription** (Whisper) | [console.groq.com](https://console.groq.com) |
| `gemini` | LLM (Gemini direct) | [aistudio.google.com](https://aistudio.google.com) |


<details>
<summary><b>Full config example</b></summary>

```json
{
  "agents": {
    "defaults": {
      "model": "anthropic/claude-opus-4-5"
    }
  },
  "providers": {
    "openrouter": {
      "apiKey": "sk-or-v1-xxx"
    },
    "groq": {
      "apiKey": "gsk_xxx"
    }
  },
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "123456:ABC...",
      "allowFrom": ["123456789"]
    },
    "whatsapp": {
      "enabled": false
    },
    "wecom": {
      "enabled": false,
      "corpId": "",
      "agentId": 0,
      "secret": "",
      "allowFrom": []
    }
  },
  "tools": {
    "web": {
      "search": {
        "apiKey": "BSA..."
      }
    }
  }
}
```

</details>

<details>
<summary><b>模型配置 (Model)</b></summary>

Agent 的推理能力（含 gateway、agent 命令、cron、heartbeat）统一使用 `agents.defaults.model`。

**配置位置**：`~/.nanobot/config.json` → `agents.defaults.model`

**推荐强大模型**（需对应 provider 的 apiKey）：
- `anthropic/claude-opus-4-5` - Claude 最强（Anthropic API）
- `anthropic/claude-sonnet-4` - 平衡
- `openai/gpt-4o` - GPT-4o（OpenAI API）
- `openai/gpt-4o-mini` - 轻量

**通过 OpenRouter**（一个 key 访问多种模型）：
```json
{
  "providers": {
    "openrouter": {
      "apiKey": "sk-or-v1-xxx"
    }
  },
  "agents": {
    "defaults": {
      "model": "anthropic/claude-opus-4-5"
    }
  }
}
```

修改后需**重启 gateway** 生效。

</details>

## CLI Reference

| Command | Description |
|---------|-------------|
| `nanobot onboard` | Initialize config & workspace |
| `nanobot agent -m "..."` | Chat with the agent |
| `nanobot agent` | Interactive chat mode |
| `nanobot gateway` | Start the gateway |
| `nanobot status` | Show status |
| `nanobot knowledge ingest` | Import documents into knowledge base (default: workspace/knowledge) |
| `nanobot knowledge status` | Show knowledge base chunk count |
| `nanobot knowledge clear-web-cache` | Clear web search cache (normally auto-cleared weekly) |
| `nanobot channels login` | Link WhatsApp (scan QR) |
| `nanobot channels status` | Show channel status |

<details>
<summary><b>Scheduled Tasks (Cron)</b></summary>

```bash
# Add a job
nanobot cron add --name "daily" --message "Good morning!" --cron "0 9 * * *"
nanobot cron add --name "hourly" --message "Check status" --every 3600

# List jobs
nanobot cron list

# Remove a job
nanobot cron remove <job_id>
```

</details>

## 🐳 Docker

> [!TIP]
> The `-v ~/.nanobot:/root/.nanobot` flag mounts your local config directory into the container, so your config and workspace persist across container restarts.

Build and run nanobot in a container:

```bash
# Build the image
docker build -t nanobot .

# Initialize config (first time only)
docker run -v ~/.nanobot:/root/.nanobot --rm nanobot onboard

# Edit config on host to add API keys
vim ~/.nanobot/config.json

# Run gateway (connects to Telegram/WhatsApp)
docker run -v ~/.nanobot:/root/.nanobot -p 18790:18790 nanobot gateway

# Or run a single command
docker run -v ~/.nanobot:/root/.nanobot --rm nanobot agent -m "Hello!"
docker run -v ~/.nanobot:/root/.nanobot --rm nanobot status
```

## 📁 Project Structure

```
nanobot/
├── agent/          # 🧠 Core agent logic
│   ├── loop.py     #    Agent loop (LLM ↔ tool execution)
│   ├── context.py  #    Prompt builder
│   ├── memory.py   #    Persistent memory
│   ├── skills.py   #    Skills loader
│   ├── subagent.py #    Background task execution
│   └── tools/      #    Built-in tools (incl. spawn)
├── skills/         # 🎯 Bundled skills (github, weather, tmux...)
├── channels/       # 📱 Chat channels
│   ├── telegram.py #    Telegram bot
│   ├── whatsapp.py #    WhatsApp (Node bridge)
│   ├── wecom.py    #    企业微信
│   └── shangwang.py#    商网办公 (CDP bridge)
├── bus/            # 🚌 Message routing
├── cron/           # ⏰ Scheduled tasks
├── heartbeat/      # 💓 Proactive wake-up
├── providers/      # 🤖 LLM providers (OpenRouter, etc.)
├── session/        # 💬 Conversation sessions
├── config/         # ⚙️ Configuration
├── cli/            # 🖥️ Commands
shangwang-bridge/   # 🔌 CDP bridge for AVIC Office
├── cdp.py          #    CDP client (JS hook injection)
├── server.py       #    WebSocket server (bridge ↔ nanobot)
├── config.py       #    Bridge configuration
└── main.py         #    Entry point
```

## 🤝 Contribute & Roadmap

PRs welcome! The codebase is intentionally small and readable. 🤗

**Roadmap** — Pick an item and [open a PR](https://github.com/HKUDS/nanobot/pulls)!

- [x] **Voice Transcription** — Support for Groq Whisper (Issue #13)
- [ ] **Multi-modal** — See and hear (images, voice, video)
- [ ] **Long-term memory** — Never forget important context
- [ ] **Better reasoning** — Multi-step planning and reflection
- [ ] **More integrations** — Discord, Slack, email, calendar
- [ ] **Self-improvement** — Learn from feedback and mistakes

### Contributors
