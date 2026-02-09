"""
Local knowledge store: chunk documents, embed with BGE-small-zh, store in ChromaDB.

Requires: pip install nanobot-ai[rag]
"""

from pathlib import Path
from typing import Any

# Approximate tokens to chars for Chinese (BGE/sentence-transformers)
CHARS_PER_TOKEN = 2
COLLECTION_NAME = "nanobot_kb"
SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".xlsx"}


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text into overlapping chunks (sizes in tokens, converted to chars)."""
    if not text.strip():
        return []
    size_chars = chunk_size * CHARS_PER_TOKEN
    overlap_chars = overlap * CHARS_PER_TOKEN
    step = max(1, size_chars - overlap_chars)
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size_chars, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks


def _load_text(path: Path) -> str:
    """Load plain text or markdown."""
    return path.read_text(encoding="utf-8", errors="replace")


def _load_pdf(path: Path) -> str:
    """Load PDF text via pypdf."""
    from pypdf import PdfReader
    reader = PdfReader(path)
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n\n".join(parts)


def _load_docx(path: Path) -> str:
    """Load Word document text."""
    from docx import Document
    doc = Document(path)
    return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())


def _load_xlsx(path: Path) -> str:
    """Load Excel sheet text (all sheets, cell values joined)."""
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    parts = []
    for sheet in wb.worksheets:
        for row in sheet.iter_rows(values_only=True):
            parts.append(" ".join(str(c) if c is not None else "" for c in row))
    return "\n\n".join(parts)


def _load_document(path: Path) -> str:
    """Load document content by extension."""
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(str(path))
    suffix = path.suffix.lower()
    if suffix in (".txt", ".md"):
        return _load_text(path)
    if suffix == ".pdf":
        return _load_pdf(path)
    if suffix == ".docx":
        return _load_docx(path)
    if suffix == ".xlsx":
        return _load_xlsx(path)
    raise ValueError(f"Unsupported format: {suffix}. Supported: {SUPPORTED_EXTENSIONS}")


def get_rag_import_error() -> str | None:
    """
    Return None if RAG deps are OK, else a short message (e.g. "chromadb" or "sentence_transformers").
    """
    try:
        import chromadb
    except ImportError as e:
        return f"chromadb ({e!s})"
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        return f"sentence_transformers ({e!s})"
    return None


def get_store(
    workspace: Path,
    chunk_size: int = 512,
    chunk_overlap: int = 200,
    top_k: int = 5,
) -> "KnowledgeStore | None":
    """
    Return a KnowledgeStore if RAG dependencies are installed, else None.
    """
    if get_rag_import_error() is not None:
        return None
    return KnowledgeStore(
        workspace=Path(workspace),
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        top_k=top_k,
    )


class KnowledgeStore:
    """
    Chunk documents, embed with BGE-small-zh, store and query via ChromaDB.
    Data is stored under workspace/knowledge_db.
    """

    def __init__(
        self,
        workspace: Path,
        chunk_size: int = 512,
        chunk_overlap: int = 200,
        top_k: int = 5,
    ):
        self.workspace = Path(workspace)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.top_k = top_k
        self._db_path = self.workspace / "knowledge_db"
        self._db_path.mkdir(parents=True, exist_ok=True)
        self._client = None
        self._collection = None
        self._model = None

    def _get_client(self):
        import chromadb
        from chromadb.config import Settings
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=str(self._db_path),
                settings=Settings(anonymized_telemetry=False),
            )
        return self._client

    def _get_collection(self):
        if self._collection is None:
            client = self._get_client()
            # hnsw:search_ef 提高检索召回，避免 n_results 较小时漏掉相关文档
            self._collection = client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={
                    "description": "nanobot local knowledge base",
                    "hnsw:search_ef": 64,
                },
            )
        return self._collection

    def _get_model(self):
        if self._model is None:
            self._model = __import__("sentence_transformers").SentenceTransformer(
                "BAAI/bge-small-zh-v1.5"
            )
        return self._model

    def _embed(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        embeddings = model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def add_documents(
        self,
        paths: list[Path],
        *,
        skip_unsupported: bool = True,
    ) -> dict[str, Any]:
        """
        Ingest files/directories: load, chunk, embed, add to ChromaDB.
        Returns summary: added_count, skipped, errors.
        """
        added = 0
        skipped: list[str] = []
        errors: list[str] = []

        all_chunks: list[str] = []
        all_metadatas: list[dict] = []
        all_ids: list[str] = []

        for p in paths:
            path = Path(p).resolve()
            if not path.exists():
                errors.append(f"Not found: {path}")
                continue
            if path.is_file():
                to_process = [path]
            else:
                to_process = [
                    f for f in path.rglob("*")
                    if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
                ]
            for fp in to_process:
                try:
                    text = _load_document(fp)
                except Exception as e:
                    errors.append(f"{fp}: {e}")
                    continue
                if not text.strip():
                    skipped.append(str(fp))
                    continue
                chunks = _chunk_text(text, self.chunk_size, self.chunk_overlap)
                rel = fp.relative_to(path if path.is_dir() else path.parent)
                for i, c in enumerate(chunks):
                    doc_id = f"{rel!s}_{i}".replace("\\", "/")
                    all_ids.append(doc_id)
                    all_chunks.append(c)
                    all_metadatas.append({"source": str(rel), "chunk": i})

        if not all_chunks:
            return {"added": 0, "skipped": skipped, "errors": errors}

        coll = self._get_collection()
        embeddings = self._embed(all_chunks)
        coll.add(
            ids=all_ids,
            documents=all_chunks,
            embeddings=embeddings,
            metadatas=all_metadatas,
        )
        added = len(all_chunks)
        return {"added": added, "skipped": skipped, "errors": errors}

    def search(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        """Return top-k most relevant chunks with content and source."""
        k = top_k if top_k is not None else self.top_k
        coll = self._get_collection()
        n = coll.count()
        if n == 0:
            return []
        q_emb = self._embed([query])
        results = coll.query(
            query_embeddings=q_emb,
            n_results=min(k, n),
            include=["documents", "metadatas", "distances"],
        )
        if not results or not results["ids"] or not results["ids"][0]:
            return []
        out = []
        for i, doc_id in enumerate(results["ids"][0]):
            meta = (results["metadatas"][0] or [{}])[i]
            dist = (results["distances"][0] or [0])[i]
            doc = (results["documents"][0] or [""])[i]
            out.append({
                "content": doc,
                "source": meta.get("source", ""),
                "chunk": meta.get("chunk", 0),
                "distance": float(dist),
            })
        return out

    def count(self) -> int:
        """Total number of chunks in the collection."""
        try:
            return self._get_collection().count()
        except Exception:
            return 0
