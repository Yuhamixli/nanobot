"""Chrome DevTools Protocol (CDP) client for Avic.exe Electron app.

Connects to the Electron remote debugging port, finds the im-view page,
and provides methods to:
  - hook NIM SDK message callbacks (receive messages)
  - send text messages via NIM SDK
  - query session/contact info
"""

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine

import aiohttp

logger = logging.getLogger("shangwang-cdp")

# JS: Diagnose the page structure before hooking
_DIAGNOSE_SCRIPT = r"""
(function() {
    var info = {hasVueApp: false, hasStore: false, storeKeys: [], nimKeys: [], vueVersion: ''};
    try {
        var el = document.querySelector('#app');
        if (el) {
            // Vue 2: el.__vue__
            if (el.__vue__) {
                info.hasVueApp = true;
                info.vueVersion = '2';
                var vm = el.__vue__;
                if (vm.$store) {
                    info.hasStore = true;
                    var state = vm.$store.state;
                    info.storeKeys = Object.keys(state).slice(0, 50);
                    // Look for NIM instance in store state
                    Object.keys(state).forEach(function(k) {
                        try {
                            var v = state[k];
                            if (v && typeof v === 'object') {
                                if (typeof v.sendText === 'function') {
                                    info.nimKeys.push('state.' + k + ' (has sendText)');
                                }
                                // Check nested: state.xxx.nim
                                Object.keys(v).forEach(function(k2) {
                                    try {
                                        var v2 = v[k2];
                                        if (v2 && typeof v2 === 'object' && typeof v2.sendText === 'function') {
                                            info.nimKeys.push('state.' + k + '.' + k2 + ' (has sendText)');
                                        }
                                    } catch(e) {}
                                });
                            }
                        } catch(e) {}
                    });
                    // Also check store getters
                    if (vm.$store.getters) {
                        var gk = Object.keys(vm.$store.getters).filter(function(k) {
                            return k.toLowerCase().indexOf('nim') >= 0 || k.toLowerCase().indexOf('sdk') >= 0;
                        });
                        if (gk.length) info.nimGetters = gk;
                    }
                }
            }
            // Vue 3
            if (el.__vue_app__) {
                info.hasVueApp = true;
                info.vueVersion = '3';
                try {
                    var store = el.__vue_app__.config.globalProperties.$store;
                    if (store && store.state) {
                        info.hasStore = true;
                        info.storeKeys = Object.keys(store.state).slice(0, 50);
                    }
                } catch(e) {}
            }
        }
        // Check Avic global
        if (typeof Avic !== 'undefined') {
            info.hasAvic = true;
            info.avicKeys = Object.keys(Avic).slice(0, 30);
            // Check if Avic has sendSdpCmd
            if (typeof Avic.sendSdpCmd === 'function') info.hasSendSdpCmd = true;
        }
        // Check for NIM on window
        ['nim', 'NIM', 'nimSdk', 'netease'].forEach(function(k) {
            if (window[k]) info.nimKeys.push('window.' + k);
        });
    } catch(e) {
        info.error = e.message;
    }
    return JSON.stringify(info);
})()
"""

# JS injected into im-view renderer to hook messages via multiple strategies
_HOOK_SCRIPT = r"""
(function() {
    // Force re-hook (clear previous state)
    window.__NANOBOT_MSG_QUEUE__ = window.__NANOBOT_MSG_QUEUE__ || [];
    var methods = [];

    // Helper: find NIM SDK instance for sending messages
    function tryFindNIM(vm, store) {
        if (window.__NANOBOT_NIM__) return; // already found
        try {
            // Search in store state
            var state = store.state;
            Object.keys(state).forEach(function(k) {
                try {
                    var v = state[k];
                    if (v && typeof v === 'object' && typeof v.sendText === 'function') {
                        window.__NANOBOT_NIM__ = v;
                        console.log('[nanobot] Found NIM at store.state.' + k);
                    }
                    if (v && typeof v === 'object' && !window.__NANOBOT_NIM__) {
                        Object.keys(v).forEach(function(k2) {
                            try {
                                var v2 = v[k2];
                                if (v2 && typeof v2 === 'object' && typeof v2.sendText === 'function') {
                                    window.__NANOBOT_NIM__ = v2;
                                    console.log('[nanobot] Found NIM at store.state.' + k + '.' + k2);
                                }
                            } catch(e) {}
                        });
                    }
                } catch(e) {}
            });
            // Search in Vuex modules (store._modules)
            if (!window.__NANOBOT_NIM__ && store._modules && store._modules.root) {
                function searchModules(mod, path) {
                    if (!mod || !mod._children) return;
                    Object.keys(mod._children).forEach(function(k) {
                        var child = mod._children[k];
                        if (child && child.state) {
                            Object.keys(child.state).forEach(function(sk) {
                                try {
                                    var v = child.state[sk];
                                    if (v && typeof v === 'object' && typeof v.sendText === 'function') {
                                        window.__NANOBOT_NIM__ = v;
                                        console.log('[nanobot] Found NIM at module ' + path + '/' + k + '.' + sk);
                                    }
                                } catch(e) {}
                            });
                        }
                        searchModules(child, path + '/' + k);
                    });
                }
                searchModules(store._modules.root, 'root');
            }
        } catch(e) {}
    }

    function pushMsg(msg) {
        window.__NANOBOT_MSG_QUEUE__.push(msg);
    }

    // ========== Strategy 1: Vuex store.subscribe ==========
    function tryVuexSubscribe() {
        var store = null;
        try {
            var el = document.querySelector('#app');
            if (el && el.__vue__ && el.__vue__.$store) {
                store = el.__vue__.$store;  // Vue 2
                // Also find NIM instance from Vue component tree
                tryFindNIM(el.__vue__, store);
            } else if (el && el.__vue_app__) {
                store = el.__vue_app__.config.globalProperties.$store;  // Vue 3
            }
        } catch(e) {}

        if (!store) return false;
        window.__NANOBOT_STORE__ = store;

        // Record install time to skip historical messages
        var hookTime = Date.now();
        window.__NANOBOT_HOOK_TIME__ = hookTime;

        // Track seen idClients to dedup
        var seenIds = {};

        // Subscribe to mutations - only catch actual new incoming messages
        store.subscribe(function(mutation, state) {
            try {
                var type = mutation.type || '';

                // Only care about specific message-related mutations
                // Skip session/UI state mutations that don't contain real messages
                var isNewMsg = (
                    type.indexOf('updateNewMsg') >= 0 ||
                    type.indexOf('onReceiveMsg') >= 0 ||
                    type.indexOf('putMsg') >= 0 ||
                    type.indexOf('addMsg') >= 0 ||
                    type.indexOf('receiveMsg') >= 0 ||
                    type.indexOf('onMsg') >= 0 ||
                    type.indexOf('updateCurrSessionMsgs') >= 0
                );

                // Broader fallback: mutation has 'Msg' in name AND payload looks like a message
                if (!isNewMsg && (type.indexOf('Msg') >= 0 || type.indexOf('msg') >= 0)) {
                    var p = mutation.payload;
                    if (p && typeof p === 'object' && (p.text || p.from || p.fromNick) && p.time) {
                        isNewMsg = true;
                    }
                }

                if (!isNewMsg) return;

                var payload = mutation.payload;
                if (!payload) return;

                // Handle single message object or array
                var msgs = Array.isArray(payload) ? payload : (payload.msg ? [payload.msg] : [payload]);

                msgs.forEach(function(msg) {
                    if (!msg || typeof msg !== 'object') return;

                    // Must have actual text content
                    var text = msg.text || '';
                    if (!text || typeof text !== 'string' || text.length < 1) return;

                    // Skip JSON-only payloads (system data, not chat messages)
                    if (text.charAt(0) === '{' || text.charAt(0) === '[') return;

                    var from = msg.from || msg.fromAccount || msg.account || '';
                    var sessionId = msg.sessionId || msg.to || '';
                    var msgTime = msg.time || 0;

                    // Skip messages older than hook install time (historical)
                    if (msgTime && msgTime < hookTime - 5000) return;

                    // Dedup by idClient
                    var idClient = msg.idClient || msg.id || '';
                    if (idClient && seenIds[idClient]) return;
                    if (idClient) seenIds[idClient] = true;

                    // Must have a valid session (p2p or team)
                    if (!sessionId || sessionId.indexOf('p2p') < 0 && sessionId.indexOf('team') < 0) return;

                    pushMsg({
                        type: 'msg',
                        source: 'vuex',
                        mutationType: type,
                        sessionId: sessionId,
                        from: from,
                        fromNick: msg.fromNick || msg.nick || '',
                        text: text,
                        msgType: msg.type || 'text',
                        time: msgTime || Date.now(),
                        idClient: idClient,
                        flow: msg.flow || ''
                    });
                });
            } catch(e) {}
        });
        return true;
    }

    // ========== Strategy 2: DOM MutationObserver on chat messages ==========
    function tryDOMObserver() {
        // Find the chat message container (usually a scrollable list)
        var container = document.querySelector('.session-chat') ||
                        document.querySelector('.msg-list') ||
                        document.querySelector('.chat-messages') ||
                        document.querySelector('[class*="message-list"]') ||
                        document.querySelector('[class*="chat-list"]') ||
                        document.querySelector('[class*="msg-wrap"]');

        if (!container) {
            // Broader search: find scrollable container in right pane
            var candidates = document.querySelectorAll('[style*="overflow"], [class*="scroll"]');
            for (var i = 0; i < candidates.length; i++) {
                if (candidates[i].scrollHeight > 300 && candidates[i].children.length > 2) {
                    container = candidates[i];
                    break;
                }
            }
        }

        if (!container) return false;
        window.__NANOBOT_CHAT_CONTAINER__ = container;

        var lastChildCount = container.children.length;
        var observer = new MutationObserver(function(mutations) {
            try {
                // Only care about new children (new messages)
                if (container.children.length <= lastChildCount) {
                    lastChildCount = container.children.length;
                    return;
                }
                // Extract text from newly added elements
                var newCount = container.children.length - lastChildCount;
                lastChildCount = container.children.length;

                for (var i = container.children.length - newCount; i < container.children.length; i++) {
                    var el = container.children[i];
                    if (!el) continue;
                    var text = (el.innerText || el.textContent || '').trim();
                    if (!text || text.length < 1 || text.length > 2000) continue;

                    // Try to extract sender name and message content
                    var parts = text.split('\n').filter(function(s) { return s.trim(); });
                    var sender = parts.length > 1 ? parts[0].trim() : '';
                    var content = parts.length > 1 ? parts.slice(1).join('\n').trim() : text;

                    // Skip if it looks like a time label only
                    if (/^\d{1,2}:\d{2}$/.test(content) || /^\d{4}/.test(content)) continue;

                    pushMsg({
                        type: 'msg',
                        source: 'dom',
                        sessionId: 'current',
                        from: sender,
                        fromNick: sender,
                        text: content,
                        msgType: 'text',
                        time: Date.now(),
                        idClient: 'dom_' + Date.now() + '_' + i
                    });
                }
            } catch(e) {}
        });

        observer.observe(container, { childList: true, subtree: false });
        window.__NANOBOT_DOM_OBSERVER__ = observer;
        return true;
    }

    // ========== Strategy 3: Intercept Avic.sendSdpCmd if available ==========
    function tryAvicHook() {
        if (typeof Avic === 'undefined' || !Avic.sendSdpCmd) return false;
        // Avic.sendSdpCmd is used for SDP protocol commands
        // We don't hook it for receiving, but store reference for sending
        window.__NANOBOT_AVIC__ = Avic;
        return true;
    }

    // Execute all strategies
    if (tryVuexSubscribe()) methods.push('vuex');
    if (tryDOMObserver()) methods.push('dom');
    if (tryAvicHook()) methods.push('avic');

    window.__NANOBOT_HOOKED_METHODS__ = methods;

    return JSON.stringify({
        ok: methods.length > 0,
        msg: methods.length > 0 ? 'hooked via: ' + methods.join(', ') : 'no hook method succeeded',
        methods: methods
    });
})()
"""

# JS to poll queued messages
_POLL_SCRIPT = r"""
(function() {
    var q = window.__NANOBOT_MSG_QUEUE__ || [];
    window.__NANOBOT_MSG_QUEUE__ = [];
    return JSON.stringify(q);
})()
"""

# JS to send a text message (returns result JSON)
_SEND_SCRIPT_TEMPLATE = r"""
(function() {{
    var nim = window.__NANOBOT_NIM__;

    // If NIM not found yet, try to find it from store
    if (!nim) {{
        try {{
            var el = document.querySelector('#app');
            var store = el && el.__vue__ && el.__vue__.$store;
            if (store) {{
                var state = store.state;
                var keys = Object.keys(state);
                for (var i = 0; i < keys.length; i++) {{
                    var v = state[keys[i]];
                    if (v && typeof v === 'object' && typeof v.sendText === 'function') {{
                        nim = v;
                        window.__NANOBOT_NIM__ = v;
                        break;
                    }}
                    if (v && typeof v === 'object') {{
                        var k2s = Object.keys(v);
                        for (var j = 0; j < k2s.length; j++) {{
                            try {{
                                var v2 = v[k2s[j]];
                                if (v2 && typeof v2 === 'object' && typeof v2.sendText === 'function') {{
                                    nim = v2;
                                    window.__NANOBOT_NIM__ = v2;
                                    break;
                                }}
                            }} catch(e) {{}}
                        }}
                        if (nim) break;
                    }}
                }}
                // Also search Vuex modules
                if (!nim && store._modules && store._modules.root && store._modules.root._children) {{
                    var mods = store._modules.root._children;
                    var modKeys = Object.keys(mods);
                    for (var m = 0; m < modKeys.length && !nim; m++) {{
                        var mod = mods[modKeys[m]];
                        if (mod && mod.state) {{
                            var msKeys = Object.keys(mod.state);
                            for (var n = 0; n < msKeys.length; n++) {{
                                try {{
                                    var mv = mod.state[msKeys[n]];
                                    if (mv && typeof mv === 'object' && typeof mv.sendText === 'function') {{
                                        nim = mv;
                                        window.__NANOBOT_NIM__ = mv;
                                        break;
                                    }}
                                }} catch(e) {{}}
                            }}
                        }}
                    }}
                }}
            }}
        }} catch(e) {{}}
    }}

    if (!nim) return JSON.stringify({{ok: false, error: 'NIM instance not found in store'}});

    var sessionId = {session_id};
    var text = {text};

    return new Promise(function(resolve) {{
        if (typeof nim.sendText === 'function') {{
            nim.sendText({{
                scene: sessionId.startsWith('team-') ? 'team' : 'p2p',
                to: sessionId.replace(/^(p2p-|team-)/, ''),
                text: text,
                done: function(err, msg) {{
                    if (err) {{
                        resolve(JSON.stringify({{ok: false, error: err.message || String(err)}}));
                    }} else {{
                        resolve(JSON.stringify({{ok: true, idClient: (msg && msg.idClient) || ''}}));
                    }}
                }}
            }});
        }} else {{
            resolve(JSON.stringify({{ok: false, error: 'nim.sendText not available'}}));
        }}
    }});
}})()
"""

# JS to get current session info (Vue 2 & 3)
_SESSION_INFO_SCRIPT = r"""
(function() {
    try {
        var app = document.querySelector('#app');
        var store = null;
        if (app && app.__vue_app__) {
            store = app.__vue_app__.config.globalProperties.$store;
        } else if (app && app.__vue__ && app.__vue__.$store) {
            store = app.__vue__.$store;
        }
        if (store && store.state) {
            var state = store.state;
            var currSession = state.currSessionId || state.currentSessionId || '';
            var sessions = [];
            var list = state.sessionList || state.sessions || [];
            for (var i = 0; i < Math.min(list.length, 30); i++) {
                var s = list[i];
                sessions.push({
                    id: s.id || s.sessionId || '',
                    name: s.name || s.nick || s.title || '',
                    lastMsg: (s.lastMsg && s.lastMsg.text) || (s.lastMsg && s.lastMsg.content) || '',
                    unread: s.unread || 0
                });
            }
            return JSON.stringify({ok: true, currSession: currSession, sessions: sessions});
        }
    } catch(e) {
        return JSON.stringify({ok: false, error: e.message});
    }
    return JSON.stringify({ok: false, error: 'Vue app not found'});
})()
"""


class CDPClient:
    """Async CDP client that connects to Electron's remote debugging port."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9222):
        self.host = host
        self.port = port
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._session: aiohttp.ClientSession | None = None
        self._msg_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._ws_url: str | None = None
        self._on_console: Callable | None = None
        self._hooked = False

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    async def connect(self) -> bool:
        """Find the im-view page (with Vue store) and connect via CDP WebSocket."""
        if self._session is None:
            self._session = aiohttp.ClientSession()

        # Get list of debuggable pages
        url = f"http://{self.host}:{self.port}/json"
        try:
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                pages = await resp.json()
        except Exception as e:
            logger.error("无法连接 CDP (http://%s:%s/json): %s", self.host, self.port, e)
            logger.error("请确保 Avic.exe 以 --remote-debugging-port=%s 启动", self.port)
            return False

        # Log all available targets
        logger.info("发现 %d 个可调试 target:", len(pages))
        for i, p in enumerate(pages):
            logger.info("  [%d] type=%s title='%s' url=%s",
                         i, p.get("type", "?"), p.get("title", ""), p.get("url", "")[:80])

        # Sort targets: prefer im-view URLs, then pages with titles, then any page
        def _score(page):
            page_url = page.get("url", "")
            title = page.get("title", "")
            ptype = page.get("type", "")
            if "im-view" in page_url:
                return 0  # Best: im-view page
            if ptype == "page" and title and title != "index.html":
                return 1  # Good: named page (likely a view)
            if ptype == "page":
                return 2  # OK: generic page
            return 9  # Low priority

        candidates = sorted(pages, key=_score)

        # Try each candidate: connect, check if it has Vue/store, keep if yes
        for candidate in candidates:
            ws_url = candidate.get("webSocketDebuggerUrl")
            if not ws_url:
                continue

            title = candidate.get("title", "")
            page_url = candidate.get("url", "")[:80]
            logger.info("尝试连接: title='%s' url=%s", title, page_url)

            try:
                ws = await self._session.ws_connect(ws_url, max_msg_size=10 * 1024 * 1024)

                # Temporarily set up to evaluate JS
                self._ws = ws
                self._msg_id = 0
                self._pending = {}
                self._reader_task = asyncio.create_task(self._read_loop())

                await self._send_command("Runtime.enable")

                # Quick check: does this page have Vue app with store?
                check = await self.evaluate(
                    "(function(){"
                    "var el=document.querySelector('#app');"
                    "if(el&&el.__vue__&&el.__vue__.$store)return 'vue2';"
                    "if(el&&el.__vue_app__)return 'vue3';"
                    "return '';"
                    "})()"
                )

                if check:
                    logger.info("✓ 找到 IM 页面! title='%s' (Vue %s)", title, check)
                    self._ws_url = ws_url
                    return True
                else:
                    logger.info("  跳过: title='%s' 无 Vue app", title)
                    # Cleanup and try next
                    self._reader_task.cancel()
                    self._reader_task = None
                    await ws.close()
                    self._ws = None

            except Exception as e:
                logger.debug("  连接 '%s' 失败: %s", title, e)
                if self._reader_task:
                    self._reader_task.cancel()
                    self._reader_task = None
                self._ws = None
                continue

        logger.error("所有 target 均无 Vue app — IM 聊天页面可能尚未加载")
        logger.error("请确保已登录商网办公并打开了聊天界面")
        return False

    async def disconnect(self):
        """Close CDP connection."""
        self._hooked = False
        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None
        if self._ws:
            await self._ws.close()
            self._ws = None
        if self._session:
            await self._session.close()
            self._session = None

    async def _send_command(self, method: str, params: dict | None = None) -> dict:
        """Send a CDP command and wait for result."""
        if not self.connected:
            raise ConnectionError("CDP not connected")
        self._msg_id += 1
        msg_id = self._msg_id
        msg = {"id": msg_id, "method": method, "params": params or {}}

        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = fut
        await self._ws.send_json(msg)

        try:
            result = await asyncio.wait_for(fut, timeout=30)
            return result
        except asyncio.TimeoutError:
            self._pending.pop(msg_id, None)
            raise TimeoutError(f"CDP command timed out: {method}")

    async def _read_loop(self):
        """Background reader for CDP WebSocket messages."""
        try:
            async for msg in self._ws:
                try:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        msg_id = data.get("id")
                        if msg_id and msg_id in self._pending:
                            self._pending.pop(msg_id).set_result(data)
                        # Handle console messages (useful for debugging)
                        elif data.get("method") == "Runtime.consoleAPICalled":
                            try:
                                args = data.get("params", {}).get("args", [])
                                text = " ".join(str(a.get("value", "")) for a in args[:3])
                                if "[nanobot" in text:
                                    logger.info("Console: %s", text[:200])
                            except Exception:
                                pass
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        break
                except Exception as e:
                    logger.debug("CDP message parse error (ignored): %s", e)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("CDP read loop terminated: %s", e)

    async def evaluate(self, expression: str, await_promise: bool = False) -> Any:
        """Execute JS in the page context and return the result value."""
        params = {"expression": expression, "returnByValue": True}
        if await_promise:
            params["awaitPromise"] = True
        result = await self._send_command("Runtime.evaluate", params)
        if "error" in result:
            raise RuntimeError(f"CDP evaluate error: {result['error']}")
        r = result.get("result", {}).get("result", {})
        if r.get("subtype") == "error":
            raise RuntimeError(f"JS error: {r.get('description', r)}")
        return r.get("value")

    async def inject_hook(self) -> bool:
        """Diagnose page structure, then inject message hooks."""
        # Step 1: Diagnose
        try:
            diag_raw = await self.evaluate(_DIAGNOSE_SCRIPT)
            if diag_raw:
                diag = json.loads(diag_raw)
                logger.info("页面诊断: Vue=%s store=%s keys=%s",
                            diag.get("vueVersion", "?"),
                            diag.get("hasStore"),
                            diag.get("storeKeys", [])[:10])
                if diag.get("hasAvic"):
                    logger.info("  Avic 全局对象: %s", diag.get("avicKeys", [])[:10])
        except Exception as e:
            logger.warning("诊断脚本失败: %s", e)

        # Step 2: Inject hooks
        try:
            raw = await self.evaluate(_HOOK_SCRIPT)
            if raw:
                result = json.loads(raw)
                methods = result.get("methods", [])
                if result.get("ok"):
                    logger.info("Hook 注入成功: %s", result.get("msg", ""))
                    self._hooked = True
                    return True
                else:
                    logger.warning("Hook 未成功: %s", result.get("msg", ""))
                    return False
            else:
                logger.warning("Hook 脚本返回空")
                return False
        except Exception as e:
            logger.error("Hook 注入失败: %s", e)
            return False

    async def poll_messages(self) -> list[dict]:
        """Poll queued messages from the injected hook."""
        if not self._hooked:
            return []
        try:
            raw = await self.evaluate(_POLL_SCRIPT)
            if raw:
                msgs = json.loads(raw)
                return msgs if isinstance(msgs, list) else []
        except Exception as e:
            logger.warning("poll_messages error: %s", e)
        return []

    async def send_text(self, session_id: str, text: str) -> dict:
        """Send a text message via NIM SDK."""
        script = _SEND_SCRIPT_TEMPLATE.format(
            session_id=json.dumps(session_id),
            text=json.dumps(text),
        )
        try:
            raw = await self.evaluate(script, await_promise=True)
            if raw:
                return json.loads(raw)
            return {"ok": False, "error": "empty response"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def get_session_info(self) -> dict:
        """Get current session and session list from Vue store."""
        try:
            raw = await self.evaluate(_SESSION_INFO_SCRIPT)
            if raw:
                return json.loads(raw)
        except Exception as e:
            logger.warning("get_session_info error: %s", e)
        return {"ok": False, "error": "failed"}
