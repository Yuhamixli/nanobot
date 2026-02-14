# 商网办公 Bridge（CDP 模式）

通过 **Chrome DevTools Protocol (CDP)** 连接已登录的商网办公 (Avic.exe)，直接对接内嵌的网易云信 NIM SDK，实现消息的实时收发。

## 架构

```
用户手动登录 Avic.exe (--remote-debugging-port=9222)
        │
        ▼
┌──────────────────────────────────────┐
│  Avic.exe (Electron)                 │
│  im-view.asar → NIM SDK (WebSocket)  │
│           CDP 端口 :9222              │
└──────────┬───────────────────────────┘
           │ CDP (localhost)
           ▼
┌──────────────────────────────────┐
│  shangwang-bridge (本进程)        │
│  ├── cdp.py  → 注入 JS Hook     │
│  │   ├── 监听 NIM onMsg (收消息) │
│  │   └── 调用 NIM sendText (发)  │
│  └── server.py → WebSocket :3010 │
└──────────┬───────────────────────┘
           │ WebSocket
           ▼
┌──────────────────────────────────┐
│  nanobot gateway                  │
│  └── ShangwangChannel            │
└──────────────────────────────────┘
```

## 依赖

- Python 3.10+
- 仅需 `websockets` + `aiohttp`（无 pywinauto / pywin32 依赖）

## 安装

```bash
cd shangwang-bridge
pip install -r requirements.txt
```

## 使用步骤

### 1. 启动 Avic.exe（带调试端口）

修改桌面快捷方式的「目标」，在 exe 路径后加参数：

```
"C:\Program Files (x86)\AVIC Office\Avic.exe" --remote-debugging-port=9222
```

或在 PowerShell 中直接运行：

```powershell
& "C:\Program Files (x86)\AVIC Office\Avic.exe" --remote-debugging-port=9222
```

### 2. 手动登录商网办公

正常登录，打开聊天界面。

### 3. 启动 Bridge

```bash
python main.py
```

成功后会看到：
```
商网办公 Bridge (CDP 模式)
Bridge WebSocket: ws://0.0.0.0:3010
CDP 目标: http://127.0.0.1:9222
```

### 4. 启动 nanobot

确保 `~/.nanobot/config.json` 中：
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

- `mentionNames`: 群聊仅回复 @提及 了这些昵称的消息，私聊直接回复；空数组则回复所有群消息
- `groupReplyMaxLength`: 群聊回复最大字数（默认 200），超出自动截断

然后 `nanobot gateway`。

## 配置

环境变量或 `config.json`：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SHANGWANG_WS_HOST` | `0.0.0.0` | Bridge 监听地址 |
| `SHANGWANG_WS_PORT` | `3010` | Bridge 监听端口 |
| `SHANGWANG_CDP_HOST` | `127.0.0.1` | CDP 地址 |
| `SHANGWANG_CDP_PORT` | `9222` | CDP 端口 |
| `SHANGWANG_POLL_INTERVAL` | `3` | 消息轮询间隔(秒) |
| `SHANGWANG_FILES_DIR` | `workspace/shangwang-files` | 附件下载目录（与 nanobot workspace 统一） |
| `SHANGWANG_AVICOFFICE_CACHE` | （空） | AvicOffice 缓存目录。**推荐**在 nanobot 主配置 `~/.nanobot/config.json` 的 `channels.shangwang.avicofficeCacheDir` 中配置，bridge 会优先读取 |

## 协议

### Bridge → nanobot（上行）

```json
{"type": "message", "sender": "张三", "chat_id": "p2p-xxx", "content": "你好", "msg_type": "text", "is_group": false}
{"type": "message", "sender": "李四", "chat_id": "team-xxx", "content": "@程昱涵 帮忙查一下", "msg_type": "text", "is_group": true}
{"type": "status", "status": "ready"}
{"type": "error", "error": "..."}
{"type": "sessions", "data": {"ok": true, "currSession": "p2p-xxx", "sessions": [...]}}
```

### nanobot → Bridge（下行）

```json
{"type": "send", "chat_id": "p2p-xxx", "text": "你好"}
{"type": "sessions"}
{"type": "ping"}
{"type": "rehook"}
```

## 工作原理

1. 通过 CDP 连接 Avic.exe 的 Electron 渲染进程
2. 在 im-view 页面注入 JS，hook NIM SDK 的 `onMsg` 回调
3. 定时轮询 hook 收集到的新消息，推送给 nanobot
4. 收到 nanobot 的发送指令时，调用 NIM SDK 的 `sendText` 方法

## 技术细节

### 回显过滤 (Echo Prevention)

nanobot 通过 NIM SDK 发送的消息会被 hook 再次捕获，bridge 通过多层过滤避免自循环：

1. **flow 字段过滤**: NIM SDK 标记 `flow='out'` 的消息直接跳过
2. **账号 ID 过滤**: 比对 `msg.from` 与登录账号 ID
3. **已发文本匹配**: 维护最近 50 条已发文本的 deque，匹配则跳过
4. **时间窗口去重**: 同一 session 内 5 秒内相同文本只转发一次

### 消息 Hook 策略

注入的 JS 使用双重策略确保消息捕获：

1. **Vuex store.subscribe**: 监听 Vue 状态变更中的 NIM 消息
2. **DOM MutationObserver**: 监听聊天区域 DOM 变化作为兜底

### 当前状态 (2026-02)

- [x] CDP 连接 Avic.exe Electron 渲染进程
- [x] 自动选择 im-view 目标页面
- [x] 注入 NIM hook（收消息）
- [x] 调用 NIM sendText（发消息）
- [x] 回显过滤 + 去重
- [x] 与 nanobot gateway 双向通信
- [x] 群聊仅回复 @提及 的消息（可配置 `mentionNames`）
- [x] 图片/文件消息：自动下载（aiohttp → CDP fetch → 模拟点击下载 → AvicOffice 缓存兜底）
- [x] 附件写入 `workspace/shangwang-files`，channel 自动复制到 `knowledge/长期/来自商网`
- [ ] 会话列表管理

## 故障排除

- **CDP 连接失败**: 确认 Avic.exe 使用 `--remote-debugging-port=9222` 启动
- **NIM hook 未成功**: 可能 Vue/NIM 尚未初始化，bridge 会自动重试
- **浏览器访问 `http://localhost:9222`**: 可查看所有可调试页面
- **消息重复**: 调整 `_DEDUP_WINDOW_SEC`（默认 5 秒）
- **回复到错误会话**: 检查 sessionId 格式是否为 `p2p-xxx` 或 `team-xxx`
- **文件下载 403**: 图片通常可直连，文档类(docx/zip) NOS 可能需鉴权。Bridge 会依次尝试：1) aiohttp 直连 2) CDP 页面 fetch 3) 模拟点击下载（`<a download>` 或页面中的下载按钮）4) 从 AvicOffice 缓存复制。若仍失败，可设置 `SHANGWANG_AVICOFFICE_CACHE=C:\Zoolo\AvicOffice Files`，用户手动下载后 bridge 会从该目录复制
