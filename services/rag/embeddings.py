"""BGE-M3 embeddings for the RAG system.

The old implementation used a fitted TF-IDF vectorizer.  BGE-M3 gives the
Chinese financial corpus a real semantic embedding space, so retrieval can
match paraphrases such as "盈利质量" and "利润现金含量" instead of relying on
shared character n-grams only.
"""

from __future__ import annotations

import os
import logging
import warnings
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import numpy as np

ROOT = Path(__file__).parent.parent.parent

EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DEVICE = os.getenv("RAG_EMBEDDING_DEVICE", "").strip() or None
EMBEDDING_BATCH_SIZE = int(os.getenv("RAG_EMBEDDING_BATCH_SIZE", "16"))
EMBEDDING_DIM = int(os.getenv("RAG_EMBEDDING_DIM", "1024"))

# Xet occasionally stalls on Windows for large model files. Plain HF downloads
# are slower to start but more predictable for this app's local deployment.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TQDM_DISABLE", "1")
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
warnings.filterwarnings(
    "ignore",
    message=r"You are sending unauthenticated requests to the HF Hub.*",
)


def _has_local_model_snapshot() -> bool:
    if EMBEDDING_MODEL != "BAAI/bge-m3":
        return False
    cache_root = Path.home() / ".cache" / "huggingface" / "hub" / "models--BAAI--bge-m3"
    return any(cache_root.glob("snapshots/*/pytorch_model.bin"))


def _local_files_only() -> bool:
    raw = os.getenv("RAG_LOCAL_FILES_ONLY")
    if raw is not None:
        return raw.lower() in {"1", "true", "yes"}
    return _has_local_model_snapshot()


class EmbeddingDependencyError(RuntimeError):
    """Raised when the BGE-M3 runtime dependency is unavailable."""


@lru_cache(maxsize=1)
def _get_model():
    """Load the BGE-M3 SentenceTransformer model lazily."""
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:  # pragma: no cover - depends on local env
        raise EmbeddingDependencyError(
            "RAG 需要 sentence-transformers/torch 才能加载 BGE-M3。"
            "请安装依赖：pip install -r requirements.txt"
        ) from exc

    kwargs = {}
    if EMBEDDING_DEVICE:
        kwargs["device"] = EMBEDDING_DEVICE
    return SentenceTransformer(
        EMBEDDING_MODEL,
        local_files_only=_local_files_only(),
        **kwargs,
    )


def get_embedding_model_name() -> str:
    """Return the active embedding model name stored with each chunk."""
    return EMBEDDING_MODEL


def get_embedding_dim() -> int:
    """Return the expected dense embedding dimension for BGE-M3."""
    return EMBEDDING_DIM


def _clean_texts(texts: Iterable[str]) -> list[str]:
    return [(text or "").replace("\x00", " ").strip() for text in texts]


def encode(texts: list[str]) -> np.ndarray:
    """Encode texts into normalized BGE-M3 dense vectors.

    Returns a float32 matrix with shape ``(len(texts), 1024)`` for BGE-M3.
    Empty strings are encoded as zero vectors to keep callers simple.
    """
    cleaned = _clean_texts(texts)
    if not cleaned:
        return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)

    non_empty_indices = [i for i, text in enumerate(cleaned) if text]
    vectors = np.zeros((len(cleaned), EMBEDDING_DIM), dtype=np.float32)
    if not non_empty_indices:
        return vectors

    non_empty_texts = [cleaned[i] for i in non_empty_indices]
    model = _get_model()
    encoded = model.encode(
        non_empty_texts,
        batch_size=EMBEDDING_BATCH_SIZE,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    encoded = np.asarray(encoded, dtype=np.float32)
    if encoded.ndim == 1:
        encoded = encoded.reshape(1, -1)

    actual_dim = encoded.shape[1]
    if actual_dim != EMBEDDING_DIM:
        raise RuntimeError(
            f"BGE-M3 embedding dimension mismatch: expected {EMBEDDING_DIM}, got {actual_dim}"
        )

    for row_idx, vector_idx in enumerate(non_empty_indices):
        vectors[vector_idx] = encoded[row_idx]
    return vectors


def encode_single(text: str) -> np.ndarray:
    """Encode one text into a normalized BGE-M3 dense vector."""
    return encode([text])[0]


def cosine_similarity(query_vec: np.ndarray, doc_vecs: np.ndarray) -> np.ndarray:
    """Compute cosine similarity.

    Vectors are normalized at encode time, but this function also handles older
    non-normalized vectors defensively.
    """
    if doc_vecs.size == 0:
        return np.zeros(0, dtype=np.float32)

    query_norm = np.linalg.norm(query_vec)
    if query_norm == 0:
        return np.zeros(doc_vecs.shape[0], dtype=np.float32)

    doc_norms = np.linalg.norm(doc_vecs, axis=1)
    doc_norms[doc_norms == 0] = 1.0
    scores = np.dot(doc_vecs, query_vec) / (query_norm * doc_norms)
    return np.clip(scores, -1.0, 1.0).astype(np.float32)


def is_fitted() -> bool:
    """Compatibility shim: BGE-M3 does not need corpus fitting."""
    try:
        import sentence_transformers  # noqa: F401
        import torch  # noqa: F401
    except Exception:
        return False
    return True


def fit_vectorizer(texts: list[str] | None = None):
    """Compatibility shim for the previous TF-IDF API.

    Calling this now just validates that the BGE-M3 runtime can be loaded.
    """
    return _get_model()


def embed_text(text: str) -> np.ndarray:
    return encode_single(text)


def embed_texts(texts: list[str]) -> np.ndarray:
    return encode(texts)
