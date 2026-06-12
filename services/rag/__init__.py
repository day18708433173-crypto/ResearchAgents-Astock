"""RAG (Retrieval-Augmented Generation) module for 镜衡 debate system.

Provides lightweight semantic search over financial knowledge sources
to reduce LLM hallucination in debate and literacy Q&A contexts.

Architecture:
- Offline indexing: company profiles, industry benchmarks, concept definitions
  are fetched once and periodically refreshed (TTL-based).
- Online retrieval: at debate time, relevant chunks are retrieved from the
  vector store and injected into agent prompts.

Key components:
- embeddings.py: BGE-M3 dense embeddings for Chinese financial text
- vector_store.py: SQLite-backed vector storage with cosine similarity search
- chunker.py: Multi-strategy text chunking for different source types
- retriever.py: Multi-mode retrieval pipeline
- knowledge_index.py: Data fetching + indexing for all knowledge sources
- context_builder.py: Pre-debate context enrichment (main orchestrator hook)
- cache.py: TTL-based content cache

Usage from orchestrator:
    from services.rag.context_builder import enrich_data_card, build_enriched_prompt_section

    enriched = enrich_data_card(ticker, card)
    card["rag_context"] = enriched
    prompt_section = build_enriched_prompt_section(enriched)
"""

from services.rag.embeddings import encode_single, encode, is_fitted, fit_vectorizer
from services.rag.vector_store import init_vector_store, search, upsert_chunk
from services.rag.retriever import retrieve, build_queries_for_mode
from services.rag.context_builder import enrich_data_card, build_enriched_prompt_section
from services.rag.knowledge_index import (
    index_concept_definitions,
    index_company_profile,
    index_industry_benchmarks,
    index_knowledge_base,
    index_announcements,
    index_debate_history,
    ensure_indexed,
    bulk_index_all_stocks,
    is_rag_ready,
    FINANCIAL_CONCEPTS,
)
from services.rag.chunker import chunk_text, CHUNK_STRATEGIES
from services.rag.startup import init_rag
from services.rag.retriever import get_retrieval_stats

__all__ = [
    # Embeddings
    "encode_single",
    "encode",
    "is_fitted",
    "fit_vectorizer",
    # Vector store
    "init_vector_store",
    "search",
    "upsert_chunk",
    # Retrieval
    "retrieve",
    "build_queries_for_mode",
    # Context builder
    "enrich_data_card",
    "build_enriched_prompt_section",
    # Knowledge index
    "index_concept_definitions",
    "index_company_profile",
    "index_industry_benchmarks",
    "index_knowledge_base",
    "index_announcements",
    "index_debate_history",
    "ensure_indexed",
    "bulk_index_all_stocks",
    "is_rag_ready",
    "FINANCIAL_CONCEPTS",
    # Chunker
    "chunk_text",
    "CHUNK_STRATEGIES",
    # Startup
    "init_rag",
    # Monitoring
    "get_retrieval_stats",
]
