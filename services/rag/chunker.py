"""Multi-strategy text chunking for different knowledge source types.

Each source type has a different optimal chunk size and strategy:
- financial_report: Section-based (split on ## headings), 200-2000 chars
- company_profile: Whole-document (single chunk per company), max 2000 chars
- industry_benchmark: Whole-document (single chunk per industry), max 1500 chars
- announcement: Document-based (one chunk per announcement), max 800 chars
- concept_definition: Whole-document (single chunk per concept), max 800 chars
"""

import re

# ── Strategy configurations ──

CHUNK_STRATEGIES: dict[str, dict] = {
    "financial_report": {
        "method": "section",
        "delimiter": "\n## ",
        "min_chars": 200,
        "max_chars": 2000,
        "overlap_chars": 100,
        "description": "8季财报Markdown，按##标题分section",
    },
    "company_profile": {
        "method": "whole",
        "max_chars": 2000,
        "description": "公司业务概况，单篇",
    },
    "industry_benchmark": {
        "method": "whole",
        "max_chars": 1500,
        "description": "申万行业对标数据，单篇",
    },
    "announcement": {
        "method": "document",
        "max_chars": 800,
        "description": "公告/新闻，单篇",
    },
    "concept_definition": {
        "method": "whole",
        "max_chars": 800,
        "description": "金融概念定义，单篇",
    },
}


def chunk_text(
    text: str,
    strategy: str = "company_profile",
    metadata: dict | None = None,
) -> list[dict]:
    """Split text into chunks according to the specified strategy.

    Args:
        text: Raw text to chunk
        strategy: One of the keys in CHUNK_STRATEGIES
        metadata: Optional dict to merge into each chunk's metadata

    Returns:
        List of dicts with keys: content, metadata (merged)
    """
    if strategy not in CHUNK_STRATEGIES:
        strategy = "company_profile"  # safe default

    cfg = CHUNK_STRATEGIES[strategy]
    method = cfg["method"]
    base_meta = dict(metadata or {})

    if method == "whole":
        chunks = _chunk_whole(text, cfg, base_meta)

    elif method == "section":
        chunks = _chunk_section(text, cfg, base_meta)

    elif method == "document":
        chunks = _chunk_document(text, cfg, base_meta)

    else:
        chunks = _chunk_whole(text, cfg, base_meta)

    return chunks


def _chunk_whole(text: str, cfg: dict, base_meta: dict) -> list[dict]:
    """Single chunk for the entire document, truncated to max_chars."""
    max_chars = cfg.get("max_chars", 2000)
    content = text.strip()
    if len(content) > max_chars:
        content = content[:max_chars] + "..."
    return [{"content": content, "metadata": dict(base_meta)}]


def _chunk_section(text: str, cfg: dict, base_meta: dict) -> list[dict]:
    """Split on section delimiters, respecting min/max char bounds."""
    delimiter = cfg.get("delimiter", "\n## ")
    min_chars = cfg.get("min_chars", 200)
    max_chars = cfg.get("max_chars", 2000)

    # Split into sections
    sections = re.split(f"({delimiter})", text)

    chunks = []
    current_section = ""

    for part in sections:
        candidate = current_section + part

        if len(candidate) > max_chars and len(current_section) >= min_chars:
            # Current section is full enough — save it and start new
            chunks.append({
                "content": current_section.strip(),
                "metadata": dict(base_meta),
            })
            current_section = part
        else:
            current_section = candidate

    # Don't forget the last section
    if current_section.strip():
        content = current_section.strip()
        if len(content) > max_chars:
            content = content[:max_chars] + "..."
        chunks.append({"content": content, "metadata": dict(base_meta)})

    # Filter out chunks that are too small
    chunks = [c for c in chunks if len(c["content"]) >= min_chars]

    # If no chunks (all too small), return as single chunk
    if not chunks and text.strip():
        content = text.strip()
        if len(content) > max_chars:
            content = content[:max_chars] + "..."
        chunks = [{"content": content, "metadata": dict(base_meta)}]

    return chunks


def _chunk_document(text: str, cfg: dict, base_meta: dict) -> list[dict]:
    """Single document chunk, truncated to max_chars."""
    max_chars = cfg.get("max_chars", 800)
    content = text.strip()
    if len(content) > max_chars:
        content = content[:max_chars] + "..."
    return [{"content": content, "metadata": dict(base_meta)}]
