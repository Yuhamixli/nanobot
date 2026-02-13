"""Record chat messages for learning admin reply tone (customer vs admin)."""

import json
import re
from pathlib import Path
from typing import Any

from loguru import logger


CHAT_HISTORY_DIR = "chat_history"
ROLE_ADMIN = "admin"
ROLE_CUSTOMER = "customer"
ROLE_UNKNOWN = "unknown"


def _sanitize_filename(chat_id: str) -> str:
    """Replace invalid chars for filesystem."""
    return re.sub(r'[<>:"/\\|?*]', "_", chat_id)[:120]


class ChatHistoryRecorder:
    """Append chat messages to JSONL files, tagged by role (admin/customer)."""

    def __init__(
        self,
        workspace: Path,
        admin_names: list[str] | None = None,
        admin_ids: list[str] | None = None,
    ):
        self.workspace = Path(workspace)
        self.admin_names = set((n or "").strip() for n in (admin_names or []) if n)
        self.admin_ids = set((i or "").strip() for i in (admin_ids or []) if i)
        self._base = self.workspace / CHAT_HISTORY_DIR

    def _role(self, sender: str, sender_id: str) -> str:
        """Determine role from sender nickname or ID."""
        if not self.admin_names and not self.admin_ids:
            return ROLE_UNKNOWN
        sn = (sender or "").strip()
        sid = (sender_id or "").strip()
        if sid and sid in self.admin_ids:
            return ROLE_ADMIN
        if sn and sn in self.admin_names:
            return ROLE_ADMIN
        return ROLE_CUSTOMER

    def record(
        self,
        channel: str,
        chat_id: str,
        sender: str,
        content: str,
        role: str | None = None,
        sender_id: str = "",
        is_group: bool = False,
        timestamp: float | None = None,
        id_client: str = "",
    ) -> None:
        """Append one message to the history file. id_client for dedup when merging history."""
        if not content or not content.strip():
            return
        r = role if role else self._role(sender, sender_id)
        path = self._base / channel / f"{_sanitize_filename(chat_id)}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        import time
        ts = timestamp if timestamp is not None else time.time()
        row = {
            "ts": ts,
            "sender": sender,
            "sender_id": sender_id,
            "content": content.strip(),
            "role": r,
            "chat_id": chat_id,
            "is_group": is_group,
        }
        if id_client:
            row["id_client"] = id_client
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("Chat history write failed: %s", e)

    def diagnose(
        self,
        channel: str = "shangwang",
        chat_id_filter: str | None = None,
    ) -> dict[str, Any]:
        """Diagnose why no Q&A pairs: check role distribution and config."""
        src = self._base / channel
        result: dict[str, Any] = {
            "admin_names": list(self.admin_names),
            "admin_ids": list(self.admin_ids),
            "admin_configured": bool(self.admin_names or self.admin_ids),
            "chats": [],
            "hint": "",
        }
        if not src.exists():
            result["hint"] = "chat_history 目录不存在，请先启动 gateway 并确保有消息记录"
            return result
        for p in src.glob("*.jsonl"):
            cid = p.stem
            if chat_id_filter and cid != chat_id_filter:
                continue
            rows: list[dict] = []
            try:
                for line in p.open(encoding="utf-8"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            except OSError:
                continue
            admin_count = sum(1 for r in rows if r.get("role") == ROLE_ADMIN)
            customer_count = sum(1 for r in rows if r.get("role") == ROLE_CUSTOMER)
            unknown_count = sum(1 for r in rows if r.get("role") == ROLE_UNKNOWN)
            pairs = 0
            for i in range(len(rows) - 1):
                if rows[i].get("role") == ROLE_CUSTOMER and rows[i + 1].get("role") == ROLE_ADMIN:
                    q, r = (rows[i].get("content") or "").strip(), (rows[i + 1].get("content") or "").strip()
                    if len(q) >= 10 and len(r) >= 10:
                        pairs += 1
            result["chats"].append({
                "chat_id": cid,
                "total": len(rows),
                "admin": admin_count,
                "customer": customer_count,
                "unknown": unknown_count,
                "qa_pairs": pairs,
            })
        if not result["admin_configured"]:
            result["hint"] = "adminNames 或 adminIds 未配置，消息被标记为 unknown。请配置后运行 nanobot chat-history re-role 重新标记，再 export。"
        elif result["chats"]:
            c = result["chats"][0]
            if c.get("unknown", 0) == c["total"]:
                result["hint"] = "所有消息为 unknown（录制时未配置 admin）。请配置 adminNames/adminIds 后运行 nanobot chat-history re-role，再 export。"
            elif c["admin"] == 0:
                result["hint"] = f"该会话中无管理员消息（admin=0）。请确认 adminNames/adminIds 与实际群内管理员昵称/账号一致。"
            elif c["qa_pairs"] == 0:
                result["hint"] = f"有 {c['admin']} 条管理员消息，但无连续的「客户→管理员」对话对。可能消息顺序交错或内容过短。"
            else:
                result["hint"] = f"应可导出 {c['qa_pairs']} 对，请重试 export。"
        elif chat_id_filter:
            result["hint"] = f"未找到 chat_id={chat_id_filter} 的记录。运行 nanobot chat-history list 查看实际 ID（需完全一致）。"
        return result

    def re_role(self, channel: str = "shangwang", chat_id_filter: str | None = None) -> int:
        """Re-process all messages with current admin config. Returns count of updated rows."""
        src = self._base / channel
        if not src.exists() or (not self.admin_names and not self.admin_ids):
            return 0
        updated = 0
        for p in src.glob("*.jsonl"):
            cid = p.stem
            if chat_id_filter and cid != chat_id_filter:
                continue
            rows: list[dict] = []
            try:
                for line in p.open(encoding="utf-8"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            except OSError:
                continue
            if not rows:
                continue
            new_rows = []
            for r in rows:
                new_role = self._role(r.get("sender", ""), r.get("sender_id", ""))
                if r.get("role") != new_role:
                    r = dict(r)
                    r["role"] = new_role
                    updated += 1
                new_rows.append(r)
            try:
                with open(p, "w", encoding="utf-8") as f:
                    for r in new_rows:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
            except OSError:
                pass
        return updated

    def save_fetched_messages(
        self,
        channel: str,
        chat_id: str,
        messages: list[dict[str, Any]],
        is_group: bool = False,
    ) -> int:
        """
        Save messages from DOM/Vue fetch. Dedup by id_client or (ts, sender, content).
        Returns count of newly added rows.
        """
        path = self._base / channel / f"{_sanitize_filename(chat_id)}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        existing: set[str] = set()
        if path.exists():
            try:
                for line in path.open(encoding="utf-8"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                        ic = r.get("id_client", "")
                        if ic:
                            existing.add(ic)
                        else:
                            existing.add(f"{r.get('ts',0)}|{r.get('sender','')}|{(r.get('content','') or '')[:80]}")
                    except json.JSONDecodeError:
                        continue
            except OSError:
                pass
        added = 0
        for m in messages:
            text = (m.get("text") or "").strip()
            if not text:
                continue
            ic = m.get("idClient", "")
            ts = m.get("time", 0) or 0
            sender = m.get("fromNick", "") or m.get("from", "")
            sender_id = m.get("from", "")
            dedup_key = ic if ic else f"{ts}|{sender}|{text[:80]}"
            if dedup_key in existing:
                continue
            existing.add(dedup_key)
            r = self._role(sender, sender_id)
            row = {
                "ts": ts,
                "sender": sender,
                "sender_id": sender_id,
                "content": text,
                "role": r,
                "chat_id": chat_id,
                "is_group": is_group,
            }
            if ic:
                row["id_client"] = ic
            try:
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                added += 1
            except OSError:
                pass
        return added

    def list_chats(self, channel: str = "shangwang") -> list[dict[str, Any]]:
        """List all chat_ids in history with message count."""
        src = self._base / channel
        if not src.exists():
            return []
        result = []
        for p in src.glob("*.jsonl"):
            chat_id = p.stem
            if chat_id.startswith("."):
                continue
            try:
                count = sum(1 for _ in p.open(encoding="utf-8") if _.strip())
            except OSError:
                count = 0
            chat_type = "群聊" if chat_id.startswith("team-") else "私聊"
            result.append({"chat_id": chat_id, "msg_count": count, "type": chat_type})
        return sorted(result, key=lambda x: -x["msg_count"])

    def export_qa_pairs(
        self,
        channel: str = "shangwang",
        output_dir: Path | None = None,
        min_content_len: int = 10,
        chat_id_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Extract customer-question + admin-reply pairs from history.
        Returns list of {question, reply, chat_id, ts} for ingest.
        """
        src = self._base / channel
        if not src.exists():
            return []
        out_dir = Path(output_dir) if output_dir else self.workspace / "knowledge" / "回复示例"
        out_dir.mkdir(parents=True, exist_ok=True)
        pairs: list[dict[str, Any]] = []
        for p in src.glob("*.jsonl"):
            cid = p.stem
            if chat_id_filter and cid != chat_id_filter:
                continue
            rows: list[dict] = []
            try:
                for line in p.open(encoding="utf-8"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            except OSError:
                continue
            rows.sort(key=lambda x: x.get("ts", 0))
            # Consecutive customer -> admin = Q&A pair
            for i in range(len(rows) - 1):
                a, b = rows[i], rows[i + 1]
                if a.get("role") != ROLE_CUSTOMER or b.get("role") != ROLE_ADMIN:
                    continue
                q = (a.get("content") or "").strip()
                r = (b.get("content") or "").strip()
                if len(q) < min_content_len or len(r) < min_content_len:
                    continue
                pairs.append({
                    "question": q,
                    "reply": r,
                    "chat_id": a.get("chat_id", cid),
                    "ts": b.get("ts", 0),
                })
        if not pairs:
            return []
        # Write to markdown for knowledge ingest
        out_path = out_dir / "商网_客户问题与管理员回复.md"
        lines = [
            "# 商网群聊 客户问题与管理员回复示例",
            "",
            "以下为从群聊历史中提取的客户问题及管理员回复，供 agent 模仿回复口吻。",
            "",
            "---",
            "",
        ]
        for i, p in enumerate(pairs[:200], 1):  # Limit 200 pairs
            lines.append(f"## 示例 {i} (来源: {p['chat_id']})")
            lines.append("")
            lines.append(f"**客户**: {p['question']}")
            lines.append("")
            lines.append(f"**管理员**: {p['reply']}")
            lines.append("")
            lines.append("---")
            lines.append("")
        try:
            out_path.write_text("\n".join(lines), encoding="utf-8")
            logger.info("Exported %d Q&A pairs to %s", len(pairs), out_path)
        except OSError as e:
            logger.warning("Export write failed: %s", e)
        return pairs
