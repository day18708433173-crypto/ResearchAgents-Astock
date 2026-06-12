"""Pre-debate context enrichment.

Builds enriched context for debate agents by retrieving relevant
knowledge from the RAG vector store and formatting it for prompt injection.

Main entry point: enrich_data_card() — called from orchestrator.py
after data card generation and before debate rounds begin.
"""

from services.rag.retriever import retrieve, build_queries_for_mode
from services.rag.knowledge_index import ensure_indexed


def enrich_data_card(ticker: str, data_card: dict) -> dict:
    """Enrich a data card with RAG-retrieved context before debate.

    Called after data_card.py generates the structured financial data.
    Retrieves company profile, industry benchmarks, and announcements
    from the RAG vector store.

    Args:
        ticker: Full ticker code like "600519.SH"
        data_card: The data card dict from data_card.generate()

    Returns:
        dict with keys:
            company_profile: str — business description, industry, products
            industry_profile: str — sector PE/PB benchmarks
            recent_announcements: list[dict] — [{title, date, url}, ...]
            status: dict — what was retrieved successfully
    """
    result = {
        "company_profile": "",
        "financial_report": "",
        "industry_profile": "",
        "recent_announcements": [],
        "status": {
            "company_profile": False,
            "financial_report": False,
            "industry_profile": False,
            "announcements": False,
        },
        "index_status": {},
    }

    code = ticker.split(".")[0] if "." in ticker else ticker

    # ── Ensure sources are indexed ──
    index_status = ensure_indexed(ticker)
    result["index_status"] = index_status

    # ── Derive industry from data card or company profile ──
    industry = _extract_industry(data_card)

    # ── 1. Company profile ──
    queries = build_queries_for_mode("pre_debate", ticker, data_card)
    profile_results = retrieve(
        queries,
        mode="pre_debate",
        ticker=ticker,
        source_types=["company_profile"],
        top_k=2,
    )

    if profile_results["chunks"]:
        profiles = []
        for c in profile_results["chunks"]:
            profiles.append(c.get("content", ""))
            if not industry:
                industry = c.get("industry", "")
        result["company_profile"] = "\n\n".join(profiles)
        result["status"]["company_profile"] = True

    # ── 2. Financial report / data knowledge base ──
    report_results = retrieve(
        [
            f"{code} 财务质量 盈利能力 现金流 收入 利润 ROE 毛利率 负债率",
            f"{code} 最近季度 财报 趋势 风险 资产负债 经营现金流",
        ],
        mode="pre_debate",
        ticker=ticker,
        source_types=["financial_report"],
        top_k=4,
        min_score=0.05,
    )
    if report_results["chunks"]:
        result["financial_report"] = "\n\n".join(
            c.get("content", "") for c in report_results["chunks"][:4]
        )
        result["status"]["financial_report"] = True

    # ── 3. Industry benchmarks ──
    if industry:
        ind_results = retrieve(
            [f"{industry} 行业平均PE PB ROE"],
            mode="pre_debate",
            source_types=["industry_benchmark"],
            industry=industry,
            top_k=1,
        )
        if ind_results["chunks"]:
            result["industry_profile"] = ind_results["chunks"][0].get("content", "")
            result["status"]["industry_profile"] = True
    else:
        # Try broader industry search
        ind_results = retrieve(
            ["行业平均估值 PE PB"],
            mode="pre_debate",
            source_types=["industry_benchmark"],
            top_k=2,
        )
        if ind_results["chunks"]:
            parts = [c.get("content", "") for c in ind_results["chunks"]]
            result["industry_profile"] = "\n\n".join(parts)
            result["status"]["industry_profile"] = True

    # ── 4. Recent announcements ──
    announce_results = retrieve(
        queries,
        mode="pre_debate",
        ticker=ticker,
        source_types=["announcement"],
        top_k=5,
        min_score=0.01,  # announcements have short content, lower threshold
    )
    if announce_results["chunks"]:
        for c in announce_results["chunks"]:
            meta = {}
            try:
                import json
                meta = json.loads(c.get("metadata_json", "{}"))
            except Exception:
                pass
            result["recent_announcements"].append({
                "title": meta.get("title", ""),
                "date": meta.get("date", ""),
                "url": meta.get("url", ""),
                "summary": c.get("content", "")[:200],
            })
        result["status"]["announcements"] = True

    return result


def build_enriched_prompt_section(enriched_context: dict) -> str:
    """Build the prompt section text from enriched context.

    Formats the enriched context into a prompt-ready string that
    can be appended to the agent's system prompt or user message.

    Args:
        enriched_context: The dict returned by enrich_data_card()

    Returns:
        Formatted string for insertion into agent prompt, or empty string
        if nothing was retrieved.
    """
    sections = []

    # Company profile
    if enriched_context.get("company_profile"):
        sections.append(
            "### 公司业务概况\n"
            + enriched_context["company_profile"]
        )

    # Industry benchmarks
    if enriched_context.get("industry_profile"):
        sections.append(
            "### 行业对标数据（申万行业分类）\n"
            + enriched_context["industry_profile"]
        )

    # Financial report context
    if enriched_context.get("financial_report"):
        sections.append(
            "### 财务与经营补充材料\n"
            + enriched_context["financial_report"]
        )

    # Recent announcements
    announcements = enriched_context.get("recent_announcements", [])
    if announcements:
        lines = ["### 近期重要公告"]
        for a in announcements[:5]:
            title = a.get("title", "")
            date = a.get("date", "")
            if title:
                lines.append(f"- [{date}] {title}")
        sections.append("\n".join(lines))

    if not sections:
        return ""

    header = (
        "## 补充知识（由系统从公开信息检索，供参考）\n\n"
        "以下信息来自系统RAG知识库，可以帮助你在辩论中提供更丰富的上下文。"
        "但请注意：\n"
        "- 所有**数值型声明**仍必须以[数据卡]为准\n"
        "- 行业对标数据可用于比较分析\n"
        "- 公告信息可用于背景补充，但不能替代数据卡中的财务数据\n"
    )

    return header + "\n\n" + "\n\n".join(sections)


def retrieve_concept_explanation(term: str) -> str:
    """Retrieve concept definitions for the financial literacy Q&A.

    Args:
        term: The financial term or concept to explain

    Returns:
        Formatted explanation text, or empty string if not found
    """
    from services.rag.retriever import retrieve_concepts

    chunks = retrieve_concepts(term, top_k=2)
    if not chunks:
        return ""

    content = chunks[0].get("content", "")
    if content:
        # Clean up: remove the "金融概念：" prefix if present
        if content.startswith("金融概念："):
            content = content[len("金融概念："):]
    return content


def _extract_industry(data_card: dict) -> str:
    """Try to extract industry name from a data card.

    Looks for industry information in various possible locations within
    the data card structure.
    """
    # Check if rag_context was already attached
    rag_ctx = data_card.get("rag_context", {})
    if isinstance(rag_ctx, dict):
        # Try to find industry from company profile
        cp = rag_ctx.get("company_profile", "")
        if cp:
            for line in cp.split("\n"):
                if "所属行业" in line:
                    industry = line.split("：", 1)[-1].split(":")[-1].strip()
                    if industry:
                        return industry

    # Check if fields contain industry info
    fields = data_card.get("fields", {})
    for key in fields:
        if "行业" in key:
            val = fields[key].get("value", "")
            if val:
                return val

    return ""
