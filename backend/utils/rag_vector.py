import os
import re
import time
import json
import asyncio
import hashlib
from typing import Optional

import aiohttp
import chromadb
from chromadb.config import Settings

CHROMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "chroma_db",
)
COLLECTION_PREFIX = "rag_"
MAX_RESULTS = 5
EMBED_DIM = 3072

_chroma_client = None
_embed_cache: dict[str, tuple[list[float], float]] = {}
_EMBED_CACHE_TTL = 3600


def _get_client():
    global _chroma_client
    if _chroma_client is None:
        os.makedirs(CHROMA_PATH, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(
            path=CHROMA_PATH,
            settings=Settings(anonymized_telemetry=False),
        )
    return _chroma_client


def _collection_name(guild_id: str) -> str:
    return f"{COLLECTION_PREFIX}{guild_id}"


def _get_or_create_collection(guild_id: str):
    client = _get_client()
    name = _collection_name(guild_id)
    try:
        return client.get_collection(name)
    except (ValueError, chromadb.errors.NotFoundError):
        return client.create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )


async def _call_gemini_embed(text: str, session: Optional[aiohttp.ClientSession] = None) -> Optional[list[float]]:
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={api_key}"
    payload = {
        "model": "models/gemini-embedding-001",
        "content": {"parts": [{"text": text}]},
    }

    close_session = False
    if session is None:
        session = aiohttp.ClientSession()
        close_session = True

    try:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                data = await resp.json()
                values = data.get("embedding", {}).get("values")
                if values and len(values) == EMBED_DIM:
                    return values
            return None
    except Exception:
        return None
    finally:
        if close_session:
            await session.close()


def _fallback_embed(text: str) -> list[float]:
    text = re.sub(r"\s+", " ", text).strip().lower()
    words = text.split()
    vec = [0.0] * EMBED_DIM
    if not words:
        return vec
    for i, word in enumerate(words):
        h = int(hashlib.md5(word.encode()).hexdigest()[:8], 16)
        idx = h % EMBED_DIM
        vec[idx] += 1.0
    mag = sum(v * v for v in vec) ** 0.5
    if mag > 0:
        vec = [v / mag for v in vec]
    return vec


async def embed_text(text: str, session: Optional[aiohttp.ClientSession] = None) -> list[float]:
    now = time.time()
    cached = _embed_cache.get(text)
    if cached and now - cached[1] < _EMBED_CACHE_TTL:
        return cached[0]

    gemini_vec = await _call_gemini_embed(text, session)
    if gemini_vec:
        _embed_cache[text] = (gemini_vec, now)
        return gemini_vec

    fallback = _fallback_embed(text)
    _embed_cache[text] = (fallback, now)
    return fallback


async def add_chunks(guild_id: str, chunks: list[str], filename: str, session: Optional[aiohttp.ClientSession] = None):
    if not chunks:
        return

    collection = _get_or_create_collection(guild_id)
    existing_ids = set()
    try:
        existing = collection.get(include=[])
        existing_ids = set(existing.get("ids", []))
    except Exception:
        pass

    ids = []
    embeddings = []
    metadatas = []
    documents = []

    for i, chunk in enumerate(chunks):
        chunk_id = hashlib.md5(f"{guild_id}:{filename}:{i}:{chunk}".encode()).hexdigest()[:16]
        if chunk_id in existing_ids:
            continue
        vec = await embed_text(chunk, session)
        ids.append(chunk_id)
        embeddings.append(vec)
        metadatas.append({"filename": filename, "chunk_index": i})
        documents.append(chunk)

    if ids:
        collection.add(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=documents)


async def remove_document(guild_id: str, filename: str):
    try:
        collection = _get_or_create_collection(guild_id)
        existing = collection.get(include=["metadatas"])
        if not existing or not existing.get("ids"):
            return
        delete_ids = []
        for i, meta in enumerate(existing["metadatas"]):
            if meta and meta.get("filename") == filename:
                delete_ids.append(existing["ids"][i])
        if delete_ids:
            collection.delete(ids=delete_ids)
    except Exception:
        pass


async def remove_all(guild_id: str):
    try:
        client = _get_client()
        name = _collection_name(guild_id)
        client.delete_collection(name)
    except Exception:
        pass


async def search(guild_id: str, query: str, n_results: int = MAX_RESULTS, session: Optional[aiohttp.ClientSession] = None) -> list[dict]:
    try:
        collection = _get_or_create_collection(guild_id)
        count = collection.count()
        if count == 0:
            return []
    except Exception:
        return []

    query_vec = await embed_text(query, session)
    if not query_vec:
        return []

    try:
        results = collection.query(
            query_embeddings=[query_vec],
            n_results=min(n_results, count),
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        return []

    if not results or not results.get("ids") or not results["ids"][0]:
        return []

    output = []
    for i, doc_id in enumerate(results["ids"][0]):
        doc_text = results["documents"][0][i] if results.get("documents") else ""
        meta = results["metadatas"][0][i] if results.get("metadatas") else {}
        dist = results["distances"][0][i] if results.get("distances") else 0.0
        similarity = 1.0 - dist
        output.append({
            "id": doc_id,
            "text": doc_text,
            "filename": meta.get("filename", "unknown"),
            "similarity": round(similarity, 4),
        })

    return output


async def collection_stats(guild_id: str) -> dict:
    try:
        collection = _get_or_create_collection(guild_id)
        count = collection.count()
        return {"chunk_count": count}
    except Exception:
        return {"chunk_count": 0}