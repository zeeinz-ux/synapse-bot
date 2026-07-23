import re
import time
import hashlib
from datetime import datetime, timezone
from typing import Optional

from backend.cogs.database.firebase_setup import db

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
MAX_CHUNKS_PER_QUERY = 5
USE_VECTOR_SEARCH = True


def chunk_text(text: str) -> list[str]:
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return []
    if len(text) <= CHUNK_SIZE:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        if end >= len(text):
            chunks.append(text[start:])
            break
        split_at = text.rfind(' ', start, end)
        if split_at > start + CHUNK_SIZE // 2:
            end = split_at
        chunks.append(text[start:end])
        start = end - CHUNK_OVERLAP if end - CHUNK_OVERLAP > start else end
    return chunks


async def extract_text(file_data: bytes, filename: str) -> Optional[str]:
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext == 'txt':
        try:
            return file_data.decode('utf-8', errors='replace')
        except Exception:
            return None
    elif ext == 'pdf':
        try:
            from io import BytesIO
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(file_data))
            text = '\n'.join(page.extract_text() or '' for page in reader.pages)
            return text if text.strip() else None
        except Exception:
            return None
    return None


async def save_document(guild_id: str, filename: str, text: str, size: int) -> dict:
    import asyncio
    if db is None:
        return {"success": False, "error": "Firestore not available"}
    doc_id = hashlib.md5(f"{guild_id}:{filename}:{time.time()}".encode()).hexdigest()[:16]
    chunks = chunk_text(text)
    doc_data = {
        "filename": filename,
        "chunks": chunks,
        "size": size,
        "chunk_count": len(chunks),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        ref = db.collection("guild_settings").document(guild_id).collection("rag_documents").document(doc_id)
        await asyncio.to_thread(ref.set, doc_data)

        if USE_VECTOR_SEARCH:
            from backend.utils.rag_vector import add_chunks
            await add_chunks(guild_id, chunks, filename)

        return {"success": True, "doc_id": doc_id}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def list_documents(guild_id: str) -> list[dict]:
    if db is None:
        return []
    try:
        import asyncio
        docs = await asyncio.to_thread(
            lambda: list(db.collection("guild_settings").document(guild_id).collection("rag_documents").stream())
        )
        result = []
        for doc in docs:
            data = doc.to_dict()
            if data:
                result.append({
                    "id": doc.id,
                    "filename": data.get("filename", "unknown"),
                    "size": data.get("size", 0),
                    "chunk_count": data.get("chunk_count", 0),
                    "uploaded_at": data.get("uploaded_at", ""),
                })
        return result
    except Exception:
        return []


async def delete_document(guild_id: str, doc_id: str) -> bool:
    import asyncio
    if db is None:
        return False
    try:
        ref = db.collection("guild_settings").document(guild_id).collection("rag_documents").document(doc_id)
        doc = await asyncio.to_thread(ref.get)
        filename = doc.to_dict().get("filename", "") if doc.exists else ""
        await asyncio.to_thread(ref.delete)

        if filename and USE_VECTOR_SEARCH:
            from backend.utils.rag_vector import remove_document
            await remove_document(guild_id, filename)

        return True
    except Exception:
        return False


def search_chunks(chunks: list[str], query: str) -> list[str]:
    if not chunks:
        return []
    all_chunks = chunks
    keywords = set(w.lower() for w in query.split() if len(w) > 2)
    if not keywords:
        return all_chunks[:MAX_CHUNKS_PER_QUERY]
    scored = []
    for c in all_chunks:
        cl = c.lower()
        score = sum(kw in cl for kw in keywords)
        if score > 0:
            scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:MAX_CHUNKS_PER_QUERY]]


async def load_all_chunks(guild_id: str) -> list[str]:
    docs = await list_documents(guild_id)
    if not docs:
        return []
    if db is None:
        return []
    all_chunks = []
    try:
        import asyncio
        for doc_info in docs:
            ref = db.collection("guild_settings").document(guild_id).collection("rag_documents").document(doc_info["id"])
            doc = await asyncio.to_thread(ref.get)
            if doc.exists:
                chunks = doc.to_dict().get("chunks", [])
                all_chunks.extend(chunks)
        return all_chunks
    except Exception:
        return []


async def vector_search(guild_id: str, query: str, session=None) -> list[str]:
    from backend.utils.rag_vector import search as vector_search_
    try:
        results = await vector_search_(guild_id, query, session=session)
        if results:
            return [r["text"] for r in results]
    except Exception:
        pass
    return []


async def keyword_search(guild_id: str, query: str) -> list[str]:
    chunks = await load_all_chunks(guild_id)
    return search_chunks(chunks, query)


async def sync_existing_to_vector(guild_id: str, session=None):
    import asyncio
    from backend.utils.rag_vector import add_chunks, collection_stats

    stats = await collection_stats(guild_id)
    if stats.get("chunk_count", 0) > 0:
        return

    docs = await list_documents(guild_id)
    if not docs:
        return

    for doc_info in docs:
        ref = db.collection("guild_settings").document(guild_id).collection("rag_documents").document(doc_info["id"])
        doc = await asyncio.to_thread(ref.get)
        if doc.exists:
            data = doc.to_dict()
            chunks = data.get("chunks", [])
            filename = data.get("filename", "unknown")
            if chunks:
                await add_chunks(guild_id, chunks, filename, session)
                print(f"[RAG VECTOR] Synced {filename} ({len(chunks)} chunks) for guild {guild_id}")
