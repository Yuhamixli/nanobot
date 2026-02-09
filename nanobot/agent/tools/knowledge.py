"""Knowledge base tools: knowledge_search and knowledge_ingest."""

from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.agent.knowledge.store import get_store, SUPPORTED_EXTENSIONS

RAG_INSTALL_HINT = (
    "Local knowledge base requires RAG dependencies. "
    "Run: pip install nanobot-ai[rag]"
)


class KnowledgeSearchTool(Tool):
    """Search the local knowledge base and return relevant document chunks."""

    name = "knowledge_search"
    description = (
        "Search the local knowledge base (RAG) for relevant policy/document content. "
        "Use this when the user asks about company policies, regulations, or documents that have been imported. "
        "Returns matching text chunks with source file names."
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
        top_k: int = 5,
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


class KnowledgeIngestTool(Tool):
    """Import documents from a file or directory into the local knowledge base."""

    name = "knowledge_ingest"
    description = (
        "Import documents (PDF, Word, Excel, TXT, MD) from a path into the local knowledge base. "
        "Use a file path or the workspace 'knowledge' folder (where users place policy files). "
        "After ingest, use knowledge_search to query this content."
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
            return f"Error: path not found: {resolved}"
        try:
            result = self._store.add_documents([resolved], skip_unsupported=True)
            added = result["added"]
            errors = result.get("errors", [])
            skipped = result.get("skipped", [])
            msg = f"Ingested {added} chunk(s) from {path}."
            if errors:
                msg += f" Errors: {'; '.join(errors[:5])}"
                if len(errors) > 5:
                    msg += f" (+{len(errors) - 5} more)"
            if skipped:
                msg += f" Skipped (empty): {len(skipped)} file(s)."
            return msg
        except Exception as e:
            return f"Error ingesting: {e}"
