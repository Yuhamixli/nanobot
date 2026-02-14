# 中航小诺bot 部署与使用指南

本文档帮助你从零完成 中航小诺bot 的部署、配置与日常使用。

---

## 一、项目概述

**中航小诺bot** 是超轻量个人 AI 助手框架，具备：

- **命令行对话**：`nanobot agent -m "..."` 或交互模式
- **多通道接入**：目前接受商网办公接入（需 Node.js 与 bridge）
- **LLM 多源**：OpenRouter（推荐）、Anthropic、OpenAI、Groq、vLLM 等
- **技能与工具**：内置 Web 搜索、执行命令、技能（github、weather、tmux 等）
- **定时与心跳**：Cron 定时任务、30 分钟心跳唤醒

配置文件位置：`~/.nanobot/config.json`（Windows：`%USERPROFILE%\.nanobot\config.json`）

---

## 二、环境要求

| 项目 | 要求 |
|------|------|
| Python | ≥ 3.11 |
| 可选 | Node.js ≥ 18（仅使用 WhatsApp 时需要） |
| 可选 | Docker（容器化部署） |

---

## 三、部署方式

### 方式 A：从源码安装（推荐开发/本机使用）

```bash
cd a:\Projects\nanobot
pip install -e .
```

验证：

```bash
nanobot --version
```

### 方式 B：uv 安装（稳定、快速）

```bash
uv tool install nanobot-ai
```

### 方式 C：PyPI 安装

```bash
pip install nanobot-ai
```

### 方式 D：Docker

```bash
cd a:\Projects\nanobot
docker build -t nanobot .
```

后续步骤见「五、Docker 使用」。

---

## 四、配置与首次使用

### 4.1 初始化

在任意方式安装后执行：

```bash
nanobot onboard
```

会创建：

- `~/.nanobot/config.json`（默认配置）
- `~/.nanobot/workspace/`（默认工作区）或项目内 `c:/Projects/nanobot/workspace/`（项目模式，可随项目部署）

项目根目录下的 `config.example.json` 为完整配置模板（camelCase），可作参考或复制后改名使用。

### 4.2 填写 API 与模型

编辑 `~/.nanobot/config.json`（Windows 可用记事本或 VS Code 打开）：

```json
{
  "providers": {
    "openrouter": {
      "apiKey": "sk-or-v1-你的OpenRouter密钥"
    }
  },
  "agents": {
    "defaults": {
      "model": "anthropic/claude-opus-4-5"
    }
  }
}
```

- **API 密钥**：[OpenRouter](https://openrouter.ai/keys) 可一站使用多种模型；也可用 `anthropic`、`openai`、`groq`、`gemini` 等（见 README 配置说明）。
- **模型**：可改为 `minimax/minimax-m2` 等以降低成本。

可选：Web 搜索（Brave Search）：

```json
"tools": {
  "web": {
    "search": {
      "apiKey": "BSA-你的Brave搜索API密钥"
    }
  }
}
```

### 4.3 本地模型（vLLM）

若使用本地 vLLM：

1. 启动 vLLM：`vllm serve meta-llama/Llama-3.1-8B-Instruct --port 8000`
2. 在 `config.json` 中配置：

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

---

## 五、使用方式

### 5.1 命令行对话

单条消息：

```bash
nanobot agent -m "2+2 等于几？"
```

交互模式（多轮对话）：

```bash
nanobot agent
```

### 5.2 查看状态

```bash
nanobot status
```

可检查：配置路径、工作区、当前模型、各 Provider API 是否已配置。

### 5.3 Telegram（推荐）

1. Telegram 中找 `@BotFather` → `/newbot` → 获取 **token**。
2. 找 `@userinfobot` 获取你的 **user id**。
3. 在 `config.json` 中增加：

```json
"channels": {
  "telegram": {
    "enabled": true,
    "token": "你的Bot Token",
    "allowFrom": ["你的User ID"]
  }
}
```

4. 启动网关：

```bash
nanobot gateway
```

之后在 Telegram 中与你的 Bot 对话即可。

### 5.4 WhatsApp

- 需要 **Node.js ≥ 18**，且项目内 `bridge` 已构建（Docker 镜像中已包含）。
- 首次链接设备：
  - 本地：`nanobot channels login`，用手机 WhatsApp 扫二维码。
  - Docker：需先运行 bridge 并挂载 session 目录（见 README Docker 部分）。
- 在 `config.json` 中启用并设置 `allowFrom` 手机号。
- 运行：一个终端 `nanobot channels login`，另一个 `nanobot gateway`。

### 5.5 定时任务（Cron）

```bash
# 添加每天 9 点
nanobot cron add --name "daily" --message "早上好！" --cron "0 9 * * *"

# 按秒间隔
nanobot cron add --name "hourly" --message "检查状态" --every 3600

# 列表
nanobot cron list

# 删除
nanobot cron remove <job_id>
```

### 5.6 Docker 使用

保证宿主机有 `~/.nanobot`（或 Windows 下 `%USERPROFILE%\.nanobot`），用于持久化配置与工作区。

```bash
# 首次：初始化配置（会写入选定的目录）
docker run -v %USERPROFILE%\.nanobot:/root/.nanobot --rm nanobot onboard

# 在宿主机编辑 config.json，填入 API Key 等
notepad %USERPROFILE%\.nanobot\config.json

# 启动网关（Telegram/WhatsApp）
docker run -v %USERPROFILE%\.nanobot:/root/.nanobot -p 18790:18790 nanobot gateway

# 单次对话
docker run -v %USERPROFILE%\.nanobot:/root/.nanobot --rm nanobot agent -m "Hello!"
```

Linux/macOS 将 `%USERPROFILE%\.nanobot` 换为 `~/.nanobot` 即可。

---

## 六、配置项速查

| 配置块 | 说明 |
|--------|------|
| `providers.openrouter` | OpenRouter API Key（推荐） |
| `providers.anthropic` / `openai` / `groq` / `gemini` | 各厂商直连 |
| `providers.vllm` | 本地 vLLM：apiBase + model |
| `agents.defaults.model` | 默认模型名 |
| `channels.telegram` | token + allowFrom |
| `channels.whatsapp` | allowFrom，bridge 需单独跑 |
| `tools.web.search.apiKey` | Brave 搜索（可选） |
| `gateway.host` / `gateway.port` | 网关监听地址，默认 18790 |

完整示例见 README「Configuration → Full config example」。

---

## 七、常见问题

1. **报错：No API key configured**  
   在 `~/.nanobot/config.json` 的 `providers` 下至少配置一个 `apiKey`（如 `openrouter.apiKey`）。

2. **Windows 下找不到 config**  
   路径为 `C:\Users\你的用户名\.nanobot\config.json`，可用 `nanobot status` 查看「Config:」行。

3. **想换模型**  
   修改 `agents.defaults.model`，例如 `minimax/minimax-m2`、`anthropic/claude-sonnet-4` 等（需对应 Provider 支持）。

4. **Telegram 无回复**  
   确认 `channels.telegram.enabled` 为 true、token 正确、`allowFrom` 包含你的 user id，且 `nanobot gateway` 正在运行。

5. **语音转文字（Telegram 语音消息）**  
   配置 `providers.groq.apiKey` 后，会使用 Groq Whisper 进行转录。

6. **Windows 下 CLI 乱码或报 UnicodeEncodeError**  
   若控制台编码为 GBK，CLI 会自动使用 ASCII 替代符号（如 OK 代替 ✓）。如需 UTF-8，可在 PowerShell 中执行：`$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8`，或使用 Windows Terminal。

---

## 八、下一步

- 自定义人格与指令：编辑工作区内的 `AGENTS.md`、`SOUL.md`。
- 用户信息：编辑 `USER.md`。
- 长期记忆：使用工作区 `memory/MEMORY.md`。
- 技能与工具：见项目 `nanobot/skills/` 与 README「Project Structure」。
- **可选**：商网办公、本地知识库 (RAG) 等进阶功能见主 README「Chat Apps → 商网办公」「本地知识库」章节。

完成以上步骤后，即可完成「部署 → 配置 → 使用」全流程。
