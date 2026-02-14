"""Knowledge base tools: knowledge_search and knowledge_ingest."""

import re
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.agent.knowledge.store import get_store, SUPPORTED_EXTENSIONS


def _extract_person_name(query: str) -> str | None:
    """从「X是谁」「介绍X」等问句中提取人名，用于补充检索。"""
    q = query.strip()
    if not q or len(q) < 2:
        return None
    # 程昱涵是谁 / 程昱涵是谁啊
    m = re.match(r"^(.+?)是谁", q)
    if m:
        name = m.group(1).strip()
        if 2 <= len(name) <= 10 and not any(c in name for c in "？?！!。，,、"):
            return name
    # 介绍程昱涵 / 程昱涵的介绍
    m = re.search(r"(?:介绍|关于)\s*(.+?)(?:\s|$|。|？)", q)
    if m:
        name = m.group(1).strip()
        if 2 <= len(name) <= 10:
            return name
    return None

RAG_INSTALL_HINT = (
    "Local knowledge base requires RAG dependencies. "
    "Run: pip install nanobot-ai[rag]"
)


class KnowledgeSearchTool(Tool):
    """Search the local knowledge base and return relevant document chunks."""

    name = "knowledge_search"
    description = (
        "Search the local knowledge base (RAG) for relevant policy/document content. "
        "**Must use** when the user asks about 付款、结算、审批、资金头寸、大额支付、制度、流程、预算、账户 等业务或政策问题. "
        "Returns matching chunks with source file names. Use top_k=8~10 for better recall on business questions."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Natural language search query"},
            "top_k": {
                "type": "integer",
                "description": "Number of chunks to return (default from config)",
                "minimum": 1,
                "maximum": 20,
            },
        },
        "required": ["query"],
    }

    def __init__(
        self,
        workspace: Path,
        top_k: int = 7,
    ):
        self.workspace = Path(workspace)
        self.top_k = top_k
        self._store = get_store(self.workspace, top_k=top_k)

    async def execute(
        self,
        query: str,
        top_k: int | None = None,
        **kwargs: Any,
    ) -> str:
        if self._store is None:
            return f"Error: {RAG_INSTALL_HINT}"
        if not query.strip():
            return "Error: query cannot be empty"
        try:
            k = top_k if top_k is not None else self.top_k
            if self._store.count() == 0:
                return (
                    "知识库为空，请先导入文档：将文件放入 workspace 下的 knowledge 目录后执行 "
                    "nanobot knowledge ingest，或使用 knowledge_ingest 工具导入。"
                )
            results = self._store.search(query, top_k=k)
            # 人物类问题：补充用纯人名检索，提高 People 目录人物介绍的召回
            person_name = _extract_person_name(query)
            if person_name:
                extra = self._store.search(person_name, top_k=k)
                seen = {(r.get("content", "")[:100], r.get("source", "")) for r in results}
                for r in extra:
                    key = (r.get("content", "")[:100], r.get("source", ""))
                    if key not in seen:
                        seen.add(key)
                        results.append(r)
                results.sort(key=lambda x: x.get("distance", 999))
                results = results[:k]
            if not results:
                return f"未找到与「{query}」相关的内容，可尝试换一种问法或确认相关文档已导入知识库。"
            lines = [f"Knowledge base results for: {query}\n"]
            for i, r in enumerate(results, 1):
                lines.append(f"--- Result {i} (source: {r.get('source', '')}) ---")
                lines.append(r.get("content", "").strip())
                lines.append("")
            return "\n".join(lines).strip()
        except Exception as e:
            return f"Error searching knowledge base: {e}"


class KnowledgeListTool(Tool):
    """List source files currently in the knowledge base."""

    name = "knowledge_list"
    description = (
        "List all source files (documents) currently in the knowledge base. "
        "Use this to verify whether a document has already been ingested before replying '未检索到' or '请导入'. "
        "If the relevant file appears in the list, the document is already in the KB—suggest trying a different search query instead of asking the user to import."
    )
    parameters = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace)
        self._store = get_store(self.workspace)

    async def execute(self, **kwargs: Any) -> str:
        if self._store is None:
            return f"Error: {RAG_INSTALL_HINT}"
        try:
            sources = self._store.list_sources()
            if not sources:
                return "知识库为空，尚无已导入的文档。"
            return "知识库中已导入的文档来源：\n" + "\n".join(f"- {s}" for s in sources)
        except Exception as e:
            return f"Error listing knowledge base: {e}"


class KnowledgeIngestTool(Tool):
    """Import documents from a file or directory into the local knowledge base."""

    name = "knowledge_ingest"
    description = (
        "Import documents (PDF, Word, Excel, TXT, MD) from a path into the local knowledge base. "
        "When message contains [附件: path] (e.g. from 商网), run this first, then knowledge_get_document with the returned 'Source for retrieval' to get that document's content for summarization. "
        "When user says '放库里'/'导入知识库', run with path='knowledge' to import new files in workspace/knowledge."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "File or directory path to ingest. "
                    "Relative to workspace; e.g. 'knowledge' for the default knowledge folder."
                ),
            },
        },
        "required": ["path"],
    }

    def __init__(
        self,
        workspace: Path,
        chunk_size: int = 512,
        chunk_overlap: int = 200,
    ):
        self.workspace = Path(workspace)
        self._store = get_store(
            self.workspace,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    async def execute(self, path: str, **kwargs: Any) -> str:
        if self._store is None:
            return f"Error: {RAG_INSTALL_HINT}"
        path = path.strip()
        if not path:
            return "Error: path cannot be empty"
        resolved = (self.workspace / path).resolve()
        if not resolved.exists():
            resolved = Path(path).resolve()
        if not resolved.exists():
            return f"Error: path not found: {path}"
        try:
            result = self._store.add_documents([resolved], skip_unsupported=True)
            added = result["added"]
            errors = result.get("errors", [])
            skipped = result.get("skipped", [])
            sources = result.get("sources", [])
            msg = f"Ingested {added} chunk(s) from {path}."
            if sources:
                msg += f" Source for retrieval: {sources[0]}"
            if errors:
                msg += f" Errors: {'; '.join(errors[:5])}"
                if len(errors) > 5:
                    msg += f" (+{len(errors) - 5} more)"
            if skipped:
                msg += f" Skipped (empty): {len(skipped)} file(s)."
            return msg
        except Exception as e:
            return f"Error ingesting: {e}"


class KnowledgeGetDocumentTool(Tool):
    """获取指定文档在知识库中的全部内容，用于概述刚导入的附件。"""

    name = "knowledge_get_document"
    description = (
        "Get all chunks of a document from the knowledge base by path. "
        "Use this **immediately after knowledge_ingest** when summarizing an attachment: pass the same path or the 'Source for retrieval' from ingest result. "
        "Returns the document content for you to write a brief overview. Do NOT use knowledge_search for attachment summary—it may return other documents."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Path to the document: workspace-relative (e.g. knowledge/长期/来自商网/xxx.docx) "
                    "or the full path from [附件: ...]. Must match what was just ingested."
                ),
            },
        },
        "required": ["path"],
    }

    def __init__(
        self,
        workspace: Path,
    ):
        self.workspace = Path(workspace)
        self._store = get_store(self.workspace)

    async def execute(self, path: str, **kwargs: Any) -> str:
        if self._store is None:
            return f"Error: {RAG_INSTALL_HINT}"
        path = path.strip()
        if not path:
            return "Error: path cannot be empty"
        # 转为 workspace 相对路径（与 add_documents 中 source 格式一致）
        try:
            resolved = Path(path).resolve()
            ws = self.workspace.resolve()
            try:
                source = str(resolved.relative_to(ws)).replace("\\", "/")
            except ValueError:
                source = path.replace("\\", "/")
        except Exception:
            source = path.replace("\\", "/")
        chunks = self._store.get_document_chunks(source)
        if not chunks:
            return f"未在知识库中找到该文档: {source}。请先执行 knowledge_ingest 导入。"
        lines = [f"Document: {source}\n"]
        for i, c in enumerate(chunks, 1):
            lines.append(f"--- Chunk {i} ---")
            lines.append(c.get("content", "").strip())
            lines.append("")
        return "\n".join(lines).strip()
