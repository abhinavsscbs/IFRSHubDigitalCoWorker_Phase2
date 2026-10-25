"""Retrieval module for FAISS-backed IFRS corpora.

This module owns retrieval primitives and DB configuration. It is intentionally
independent from `engine.py` so retrieval behavior is visible in one place.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple
import os
import uuid
import json
import math
from functools import lru_cache
from pathlib import Path
from threading import RLock
import faiss

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

from .config import (DB_PATHS, EMBEDDINGS_MODEL, EMBEDDINGS_DIMENSIONS,
                     OPENAI_TIMEOUT, OPENAI_MAX_RETRIES, STAGE_2_PERCENTILE, TRUST_LOCAL_INDEXES)
from .llm_client import require_api_key


@dataclass
class DBConfig:
    path: str
    name: str
    score_threshold: float = 0.65
    top_percentile: float = STAGE_2_PERCENTILE


@lru_cache(maxsize=1)
def get_embeddings():
    return OpenAIEmbeddings(model=EMBEDDINGS_MODEL, dimensions=EMBEDDINGS_DIMENSIONS,
                            api_key=require_api_key(), request_timeout=OPENAI_TIMEOUT,
                            max_retries=OPENAI_MAX_RETRIES)


def _has_langchain_index(dir_path: str) -> bool:
    return all((Path(dir_path) / name).is_file() for name in ("index.faiss", "index.pkl"))


_INDEX_LOCK = RLock()


@lru_cache(maxsize=16)
def _load_index_cached(dir_path: str, faiss_mtime: int, pickle_mtime: int, manifest_mtime: int):
    if not TRUST_LOCAL_INDEXES:
        raise RuntimeError("Set rag.trust_local_indexes=true only for your own trusted FAISS indexes.")
    manifest = Path(dir_path) / "embedding_manifest.json"
    if not manifest.is_file():
        raise RuntimeError(f"{dir_path}: embedding_manifest.json missing. Rebuild the legacy index with scripts/rebuild_indexes.py.")
    info = json.loads(manifest.read_text(encoding="utf-8"))
    if info.get("provider") != "openai" or info.get("model") != EMBEDDINGS_MODEL or info.get("dimensions") != EMBEDDINGS_DIMENSIONS:
        raise RuntimeError(f"{dir_path}: embedding model/dimensions mismatch. Rebuild using the configured OpenAI embedder.")
    index = FAISS.load_local(dir_path, get_embeddings(), allow_dangerous_deserialization=True)
    if index.index.metric_type != faiss.METRIC_L2:
        raise RuntimeError(f"{dir_path}: expected an L2 FAISS index. Rebuild with scripts/rebuild_indexes.py.")
    if index.index.d != EMBEDDINGS_DIMENSIONS:
        raise RuntimeError(f"{dir_path}: FAISS dimension does not match the configured embeddings.")
    return index


def load_index(dir_path: str) -> FAISS:
    if not _has_langchain_index(dir_path):
        raise RuntimeError(f"{dir_path}: index.faiss and index.pkl are required.")
    path = Path(dir_path)
    # Serialize first loads; invalidate when files are replaced after rebuilding.
    with _INDEX_LOCK:
        return _load_index_cached(str(path.resolve()), (path / "index.faiss").stat().st_mtime_ns,
                                  (path / "index.pkl").stat().st_mtime_ns,
                                  (path / "embedding_manifest.json").stat().st_mtime_ns
                                  if (path / "embedding_manifest.json").exists() else 0)


_QUERY_LOCK = RLock()


@lru_cache(maxsize=256)
def _query_embedding(question: str):
    return tuple(get_embeddings().embed_query(question))


def get_query_embedding(question: str):
    # One API embedding per distinct query, shared across the five indexes and
    # both retrieval stages. Serialize cache misses to avoid a parallel stampede.
    with _QUERY_LOCK:
        return list(_query_embedding(question))


def build_retriever(dir_path: str, k: int = 5):
    vs = load_index(dir_path)
    return vs.as_retriever(search_type="similarity", search_kwargs={"k": k, "fetch_k": max(40, 5 * k)})


def retrieve_docs_with_score(
    dir_path: str,
    question: str,
    score_threshold: Optional[float] = None,
    top_percentile: Optional[float] = None,
    max_k: int = 50,
) -> List[Tuple[Document, float]]:
    """Rank squared-L2 results with 1/(1+distance), a score rather than cosine similarity."""
    vs = load_index(dir_path)
    docs_with_scores = vs.similarity_search_with_score_by_vector(get_query_embedding(question), k=max_k)

    docs_with_similarity: List[Tuple[Document, float]] = []
    for doc, distance in docs_with_scores:
        # FAISS distance: lower is better.
        # Convert distance to a stable similarity-like score in the range 0-1.
        if not math.isfinite(float(distance)):
            continue
        similarity_score = 1 / (1 + max(0.0, float(distance)))
        similarity_score = max(0.0, min(1.0, similarity_score))
        docs_with_similarity.append((doc, similarity_score))
    if top_percentile is None and score_threshold is None:
        top_percentile = STAGE_2_PERCENTILE

    if top_percentile is not None and score_threshold is None:
        sorted_docs = sorted(docs_with_similarity, key=lambda x: x[1], reverse=True)
        cutoff_index = max(1, int(len(sorted_docs) * top_percentile))
        return sorted_docs[:cutoff_index]

    if score_threshold is not None:
        return [(doc, score) for doc, score in docs_with_similarity if score >= score_threshold]

    return docs_with_similarity


def _source_tag(meta: dict, db_label: str) -> str:
    para_num = (meta or {}).get("para_number")
    if db_label in ["IFRS A", "IFRS B", "IFRS C"]:
        standard_name = (meta or {}).get("chapter_name") or (meta or {}).get("chapter") or (meta or {}).get("source") or "Document"
        if para_num and str(para_num).strip() and str(para_num).lower() not in {"none", "unnumbered"}:
            return f"({db_label} - {standard_name} - para {para_num})"
        return f"({db_label} - {standard_name})"

    chapter_name = (meta or {}).get("chapter_name") or (meta or {}).get("source") or "Document"
    header = (meta or {}).get("header", "")
    if header:
        if para_num and str(para_num).strip() and str(para_num).lower() not in {"none", "unnumbered"}:
            return f"({db_label} - {chapter_name} - {header} - para {para_num})"
        return f"({db_label} - {chapter_name} - {header})"
    if para_num and str(para_num).strip() and str(para_num).lower() not in {"none", "unnumbered"}:
        return f"({db_label} - {chapter_name} - para {para_num})"
    return f"({db_label} - {chapter_name})"


def fetch_docs(question: str, cfg: DBConfig) -> List[Document]:
    docs_with_scores = retrieve_docs_with_score(
        cfg.path,
        question,
        score_threshold=None,
        top_percentile=cfg.top_percentile,
        max_k=50,
    )

    cleaned: List[Document] = []
    for d, similarity_score in docs_with_scores:
        content = (d.page_content or "").strip()
        tag = _source_tag(d.metadata, cfg.name)
        visible_chunk = f"{tag} {content}"
        unique_id = str(uuid.uuid4())[:8]

        cleaned.append(
            Document(
                page_content=visible_chunk,
                metadata={
                    **(d.metadata or {}),
                    "source_db": cfg.name,
                    "_doc_id": unique_id,
                    "_similarity_score": similarity_score,
                },
            )
        )
    return cleaned


DBS: List[DBConfig] = [
    DBConfig(path=item["path"], name=item["name"], score_threshold=item["score_threshold"])
    for item in DB_PATHS
]
