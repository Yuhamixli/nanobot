# Bridge 图片消息支持方案

## 背景

商网办公基于网易云信 NIM SDK，当前 bridge 仅支持文本消息。用户发送图片时，bot 无法获取图片内容，导致 image_understander 等技能无法工作。

## NIM SDK 消息结构（参考官方文档）

### 图片消息
- `type`: `'image'`
- `file`: 图片对象，包含：
  - `url`: 图片下载地址（网易云信 NOS 存储）
  - `name`, `size`, `md5`, `ext`, `w`, `h`

### 当前 Hook 限制
CDP 注入的 Vuex subscribe 当前仅处理 `msg.text` 非空的消息，图片消息的 `text` 为空，直接被跳过。

---

## 设计方案

### 1. Hook 层修改（cdp.py）

**扩展消息类型**：在 Vuex 的 `msgs.forEach` 中：

```javascript
// 原逻辑：必须有 text
// 新逻辑：text 消息 或 image 消息

var text = msg.text || '';
var msgType = msg.type || 'text';
var file = msg.file || {};

// 文本消息：原有逻辑
if (msgType === 'text' && text && text.length >= 1) {
  // ... 跳过 JSON
  pushMsg({ ..., text, msgType: 'text' });
}
// 图片消息：提取 file.url
else if (msgType === 'image' && file.url) {
  pushMsg({
    type: 'msg',
    sessionId, from, fromNick, ...,
    text: '[图片]',  // 占位，便于 agent 理解
    msgType: 'image',
    fileUrl: file.url,
    fileExt: file.ext || 'jpg',
    ...
  });
}
```

### 2. Bridge server 层（server.py）

**图片下载**：收到 `msgType === 'image'` 时：

1. 用 `aiohttp` 从 `fileUrl` 下载图片
2. 存到临时目录，如 `~/.nanobot/shangwang-images/{session_id}_{idClient}.{ext}`
3. 定期清理过期文件（如 1 小时前的）
4. 将本地路径加入 payload 的 `media` 字段

**Payload 格式**：

```json
{
  "type": "message",
  "sender": "张三",
  "chat_id": "p2p-xxx",
  "content": "[图片]",
  "msg_type": "image",
  "is_group": false,
  "media": ["C:\\Users\\xxx\\.nanobot\\shangwang-images\\p2p-xxx_abc123.jpg"]
}
```

### 3. Shangwang channel 层（shangwang.py）

**传递 media**：`_handle_message` 已支持 `media` 参数，从 `data.get("media", [])` 传入即可。

### 4. Agent/Context 层

`InboundMessage` 已有 `media: list[str]` 字段，`ContextBuilder._build_user_content` 会将本地图片路径转为 base64 传给支持视觉的模型。**无需修改**。

### 5. 混合消息（图片+文字）

若 NIM 支持同一消息中图片+文字，可根据实际 mutation 结构扩展。多数场景下图片与文字是分开发送的。

---

## 实现步骤

| 步骤 | 模块 | 内容 |
|------|------|------|
| 1 | cdp.py | 修改 HOOK_SCRIPT，增加 `msgType === 'image'` 的 pushMsg，传递 `fileUrl` |
| 2 | server.py | 增加 `_download_image(url) -> path`，`_poll_messages` 中处理 image 类型 |
| 3 | server.py | 配置 `images_dir`，增加清理逻辑 |
| 4 | shangwang.py | 从 payload 取 `media` 传入 `_handle_message` |

---

## 配置项（可选）

在 bridge `config` 中可增加：

- `images_dir`: 图片缓存目录，默认 `~/.nanobot/shangwang-images`
- `image_retention_hours`: 保留时长，默认 1

---

## 依赖

- `aiohttp`：已在 requirements.txt 中
- 无需额外依赖

---

## 风险与注意

1. **URL 鉴权**：网易云信 NOS URL 可能带 token 或有时效，需在调试时确认
2. **国内网络**：NOS 为国内 CDN，bridge 运行环境需能访问
3. **磁盘占用**：可限制单会话/总缓存数量，或压缩存储
