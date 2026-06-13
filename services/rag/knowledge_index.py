"""Knowledge source ingestion and batch indexing.

Handles fetching, chunking, embedding, and storing of all RAG knowledge sources:
- Company business profiles (via akshare)
- Industry benchmarks (via akshare Shenwan sector data)
- Financial concept definitions (static curated content)
- Financial report history (via services/knowledge_base.py)
- Recent announcements (via akshare)

All data fetching is lazy and cached — re-indexing only happens when TTL expires.
"""

import os
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent.parent

# ── Suppress proxy env vars for akshare ──
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(_k, None)


# ═══════════════════════════════════════════════
#  Financial Concept Definitions (static)
# ═══════════════════════════════════════════════

FINANCIAL_CONCEPTS = [
    {
        "term": "PE(市盈率)",
        "definition": "市盈率 = 股价 ÷ 每股收益，衡量市场愿意为公司每1元盈利支付的价格。PE高说明市场对公司未来增长预期高，但估值也贵；PE低可能是价值洼地，也可能是公司基本面有问题。不同行业PE差异很大——科技股通常PE较高，银行股PE较低。",
        "usage": "辩论中声称PE高于或低于行业均值时，需结合行业特性判断——高PE不一定是坏事，低PE不一定是机会。",
        "related_terms": ["PB", "PEG", "前向PE"],
    },
    {
        "term": "PB(市净率)",
        "definition": "市净率 = 股价 ÷ 每股净资产，衡量股价相对于公司账面价值的倍数。PB<1意味着股价低于净资产（'破净'），在银行、钢铁等重资产行业常见。轻资产公司（如互联网、服务）PB通常较高，因为核心资产（品牌、技术、用户）不在资产负债表上。",
        "usage": "PB更适合评估重资产行业（银行、地产、制造业）；评估科技/服务类公司时参考意义有限。",
        "related_terms": ["PE", "ROE", "资产负债率"],
    },
    {
        "term": "ROE(净资产收益率)",
        "definition": "ROE = 净利润 ÷ 股东权益，衡量公司利用股东资金赚钱的能力。ROE 15%以上通常被认为优秀，但高ROE可能是高杠杆的结果（借钱放大收益），需要结合资产负债率一起看。巴菲特特别看重长期稳定的高ROE。",
        "usage": "辩论中ROE的判断需要拆解：高ROE来自高利润率（品牌溢价）vs 高杠杆（借钱放大）vs 高周转（薄利多销），三者含义完全不同。",
        "related_terms": ["ROIC", "资产负债率", "杜邦分析"],
    },
    {
        "term": "ROIC(投入资本回报率)",
        "definition": "ROIC = 税后营业利润 ÷ (股东权益 + 有息负债)，衡量公司使用全部投入资本（包括借来的钱）的回报效率。ROIC > WACC(加权平均资金成本)说明公司在创造价值；ROIC < WACC说明公司在毁灭价值。比ROE更全面，因为考虑了债务成本。",
        "usage": "ROIC排除了杠杆的影响，比较不同负债水平的公司时比ROE更公正。",
        "related_terms": ["ROE", "WACC", "资产负债率"],
    },
    {
        "term": "毛利率",
        "definition": "毛利率 = (营业收入 - 营业成本) ÷ 营业收入，衡量产品本身的盈利能力——卖1元产品，扣除直接成本后还剩多少。高毛利率（>50%）通常意味着品牌壁垒、技术壁垒或垄断地位；低毛利率（<20%）通常意味着竞争激烈、产品同质化。",
        "usage": "毛利率的行业差异极大——白酒70-90%，零售3-8%。跨行业比较毛利率没有意义，必须同行业对比。",
        "related_terms": ["净利率", "ROE", "营业成本"],
    },
    {
        "term": "资产负债率",
        "definition": "资产负债率 = 总负债 ÷ 总资产，衡量公司资产中有多少是通过借债获得的。50-60%在制造业中较常见；>70%需要关注偿债风险；>90%属于高杠杆运营。但银行、地产等天然高杠杆行业不适用此标准。",
        "usage": "低负债≠好——适度的杠杆可以放大ROE；高负债≠坏——要看负债结构（长期vs短期、有息vs无息）。应付账款和预收款项（无息负债）高反而是竞争优势的体现。",
        "related_terms": ["流动比率", "速动比率", "ROE"],
    },
    {
        "term": "经营现金流",
        "definition": "经营活动现金流净额是公司通过日常经营实际收到和支出的现金差额。利润可以'做'出来（通过应收账款、折旧调整等会计手段），但现金流很难造假。利润高而经营现金流为负，说明利润质量差——公司可能卖出了产品但收不到钱。",
        "usage": "利润现金含量 = 每股经营现金流 ÷ 每股收益，>1说明利润有现金支撑，<0.5需要警惕。",
        "related_terms": ["自由现金流", "利润现金含量", "应收账款"],
    },
    {
        "term": "PEG(市盈率相对盈利增长比率)",
        "definition": "PEG = PE ÷ 盈利增长率。Peter Lynch推崇的指标：PEG<1可能被低估，PEG>2可能被高估。但PEG的局限性在于：盈利增长率是历史数据或预测数据，前者不代表未来，后者依赖分析师预测的准确性。",
        "usage": "PEG适合评估成长型公司，不适合周期性公司（盈利波动大）或稳定派息型公司。",
        "related_terms": ["PE", "前向PE", "CAGR"],
    },
    {
        "term": "流动比率 / 速动比率",
        "definition": "流动比率 = 流动资产 ÷ 流动负债，衡量短期偿债能力。>2表示安全，<1表示短期偿债压力大。速动比率更保守——从流动资产中扣除存货（因为存货不一定能快速变现），>1较好。",
        "usage": "流动比率过高（>5）可能意味着资金利用效率低——大量现金闲置在账上，没有有效投资。",
        "related_terms": ["资产负债率", "存货周转率", "应收账款周转率"],
    },
    {
        "term": "自由现金流",
        "definition": "自由现金流 = 经营现金流 - 资本支出，是公司在维持现有业务后可以自由支配的现金。自由现金流充裕的公司可以分红、回购股票、并购扩张。很多'利润高'的公司自由现金流为负——因为赚的钱都用来更新设备、扩建厂房了。",
        "usage": "用自由现金流收益率（自由现金流÷市值）替代PE来估值，可以排除利润操纵的影响。",
        "related_terms": ["经营现金流", "资本支出", "利润现金含量"],
    },
    {
        "term": "换手率",
        "definition": "换手率 = 当日成交量 ÷ 流通股本，衡量股票交易的活跃程度。A股日均换手率约2-3%，>5%属于高换手，说明多空分歧大或短线资金活跃；<1%属于低换手，说明市场关注度低。",
        "usage": "换手率突然放大通常意味着重大信息正在被市场消化——可能是机会也可能是陷阱。散户主导的高换手往往伴随追涨杀跌。",
        "related_terms": ["成交量", "流通市值", "筹码集中度"],
    },
    {
        "term": "扣非净利润",
        "definition": "扣除非经常性损益后的净利润，排除了变卖资产、政府补贴、投资收益等一次性收入的影响，反映公司主营业务的真实盈利能力。如果净利润很高但扣非净利润很低，说明公司主业其实不赚钱——利润来自'意外之财'，不可持续。",
        "usage": "看利润表时应当先看扣非净利润而非净利润——后者可能被非经常性损益'美化'。",
        "related_terms": ["净利润", "非经常性损益", "经营现金流"],
    },
    {
        "term": "一致预期EPS",
        "definition": "多家券商分析师对公司未来每股收益的预测均值。代表了市场专业机构对公司盈利的集体判断。但一致预期经常偏乐观——分析师倾向于高估（因为看空报告很少），实际业绩低于一致预期的情况比高于更常见。",
        "usage": "辩论中引用一致预期时需注意其局限性——预测机构数少（<3家）时参考价值低，且分析师有乐观偏差。",
        "related_terms": ["前向PE", "PEG", "EPS"],
    },
    {
        "term": "融资融券(两融)",
        "definition": "融资=借钱买股票（做多），融券=借股票卖出（做空）。融资余额大说明市场看多情绪浓；融券余额大说明看空情绪浓。A股融券规模远小于融资（因为融券门槛高、券源少），所以两融信号以融资余额为主。",
        "usage": "融资余额快速上升可能意味着散户热情过高（危险信号）；融资余额持续下降可能意味着恐慌性去杠杆。",
        "related_terms": ["换手率", "股东户数", "资金流向"],
    },
    {
        "term": "股东户数变化",
        "definition": "股东户数是持有该股票的股东账户数量。股东户数减少 + 股价上涨 = 筹码集中（机构收集筹码），通常是积极信号；股东户数增加 + 股价下跌 = 筹码分散（散户接盘），通常是消极信号。但需要结合具体时间跨度判断。",
        "usage": "股东户数的变化方向比绝对数值更重要——连续3个季度减少比单季度减少更有参考价值。",
        "related_terms": ["户均持股", "融资融券", "换手率"],
    },
    {
        "term": "三费占比",
        "definition": "三费占比 = (销售费用 + 管理费用 + 财务费用) ÷ 营业收入。销售费用高说明公司依赖营销驱动（消费品行业常见）；管理费用高可能存在管理效率问题；财务费用高说明公司负债多、利息负担重。三费合计占营收的比例是判断公司经营效率的重要指标。",
        "usage": "三费占比突然上升需要深入分析原因——是扩张期正常投入，还是效率下降的预警？",
        "related_terms": ["毛利率", "净利率", "营业利润"],
    },
    {
        "term": "商誉",
        "definition": "商誉是公司并购时支付的对价超过被收购公司净资产公允价值的差额。商誉高说明公司进行了大量溢价并购。商誉减值测试不通过时，需要一次性计提减值损失，直接冲击当期利润。A股商誉'爆雷'是常见风险——并购标的业绩不达预期→计提商誉减值→利润断崖式下跌。",
        "usage": "商誉占总资产比例>30%的公司需要特别关注并购标的的业绩承诺是否在兑现。",
        "related_terms": ["资产负债率", "并购", "减值损失"],
    },
    {
        "term": "杜邦分析",
        "definition": "杜邦分析把ROE拆解为三个因子：ROE = 净利率 × 总资产周转率 × 权益乘数。净利率反映盈利能力（产品赚不赚钱），周转率反映运营效率（资产用得好不好），权益乘数反映杠杆水平（借了多少钱）。三个因子任何一个下降都会拉低ROE——找到ROE变化的根本原因。",
        "usage": "当辩论中讨论ROE变化时，应该用杜邦分析的框架追问：是利润率问题、效率问题、还是杠杆问题？三者对应的风险完全不同。",
        "related_terms": ["ROE", "净利率", "资产负债率"],
    },
]

# ═══════════════════════════════════════════════
#  Indexing Functions
# ═══════════════════════════════════════════════


def _ensure_embedding_ready() -> bool:
    """Ensure the BGE-M3 embedding runtime is available before indexing. Returns False on failure."""
    from services.rag.embeddings import is_fitted, fit_vectorizer

    if is_fitted():
        return True
    try:
        from services.rag.startup import _build_startup_corpus
        corpus = _build_startup_corpus()
        if not corpus:
            return False
        fit_vectorizer(corpus)
        return is_fitted()
    except Exception:
        return False


def index_concept_definitions() -> int:
    """Index all financial concept definitions into the vector store.

    These are static — once indexed, they never need refreshing.

    Returns:
        Number of concepts indexed.
    """
    from services.rag.chunker import chunk_text
    from services.rag.embeddings import encode_single
    from services.rag.vector_store import upsert_chunk, chunk_is_current

    if not _ensure_embedding_ready():
        return 0

    indexed_count = 0

    for concept in FINANCIAL_CONCEPTS:
        chunk_id = f"concept:{concept['term']}"

        # Skip if already indexed
        if chunk_is_current(chunk_id):
            indexed_count += 1
            continue

        # Build rich content text
        content = (
            f"金融概念：{concept['term']}\n\n"
            f"定义：{concept['definition']}\n\n"
            f"使用场景：{concept['usage']}\n\n"
            f"关联概念：{'、'.join(concept['related_terms'])}"
        )

        metadata = {
            "term": concept["term"],
            "related_terms": concept["related_terms"],
        }

        try:
            vec = encode_single(content)
            upsert_chunk(
                chunk_id=chunk_id,
                content=content,
                vector=vec,
                source_type="concept_definition",
                metadata=metadata,
                ttl_hours=-1,  # indefinite
            )
        except Exception:
            continue

        indexed_count += 1

    return indexed_count


def index_company_profile(ticker: str) -> bool:
    """Fetch and index company business profile for a single stock.

    Uses akshare's stock_profile_cninfo() (巨潮资讯) which returns 26 fields
    including company name, industry, listing date, main business, business scope,
    and company introduction. More stable than stock_individual_info_em().

    Args:
        ticker: Full ticker like "600519.SH" or short code like "600519"

    Returns:
        True if indexed successfully, False otherwise.
    """
    import akshare as ak
    from services.rag.cache import set_cached_json, get_cached_json

    code = ticker.split(".")[0] if "." in ticker else ticker
    cache_key = f"company_profile:{code}"

    # Check cache first
    cached = get_cached_json(cache_key)
    if cached:
        content = cached.get("content", "")
        industry = cached.get("industry", "")
    else:
        try:
            df = ak.stock_profile_cninfo(symbol=code)
            if df is None or df.empty:
                return False

            row = df.iloc[0]

            industry = str(row.get("所属行业", ""))
            full_name = str(row.get("公司名称", ""))
            main_business = str(row.get("主营业务", ""))
            business_scope = str(row.get("经营范围", ""))
            introduction = str(row.get("机构简介", ""))
            listing_date = str(row.get("上市日期", ""))
            website = str(row.get("官方网站", ""))
            legal_rep = str(row.get("法人代表", ""))
            reg_capital = str(row.get("注册资金", ""))
            index_inclusion = str(row.get("入选指数", ""))

            # Build content
            parts = []
            if full_name and full_name != "nan":
                parts.append(f"公司全称：{full_name}")
            if industry and industry != "nan":
                parts.append(f"所属行业：{industry}")
            if listing_date and listing_date != "nan":
                parts.append(f"上市日期：{listing_date}")
            if main_business and main_business != "nan":
                parts.append(f"主营业务：{main_business}")
            if business_scope and business_scope != "nan":
                parts.append(f"经营范围：{business_scope}")
            if legal_rep and legal_rep != "nan":
                parts.append(f"法人代表：{legal_rep}")
            if index_inclusion and index_inclusion != "nan":
                parts.append(f"入选指数：{index_inclusion}")
            if introduction and introduction != "nan":
                parts.append(f"公司简介：{introduction[:800]}")
            if website and website != "nan":
                parts.append(f"官网：{website}")

            content = "\n\n".join(parts) if parts else ""

            if not content:
                return False

            # Cache for 7 days
            set_cached_json(
                cache_key,
                {"content": content, "industry": industry},
                content_type="company_profile",
                ttl_hours=168,
            )
        except Exception:
            return False

    if not content:
        return False

    # Chunk and embed
    from services.rag.chunker import chunk_text
    from services.rag.embeddings import encode_single
    from services.rag.vector_store import upsert_chunk, chunk_is_current

    chunks = chunk_text(
        content,
        strategy="company_profile",
        metadata={"ticker": ticker, "industry": industry},
    )

    if not _ensure_embedding_ready():
        return False

    full_ticker = f"{code}.{'SH' if code.startswith('6') else 'SZ'}"

    for i, chunk in enumerate(chunks):
        chunk_id = f"company_profile:{code}:{i}"

        if chunk_is_current(chunk_id):
            continue

        try:
            vec = encode_single(chunk["content"])
            upsert_chunk(
                chunk_id=chunk_id,
                content=chunk["content"],
                vector=vec,
                source_type="company_profile",
                ticker=full_ticker,
                industry=industry,
                metadata={
                    **chunk.get("metadata", {}),
                    "ticker": full_ticker,
                    "industry": industry,
                },
                ttl_hours=168,  # 7 days
            )
        except Exception:
            continue

    return True


def index_industry_benchmarks() -> int:
    """Fetch and index industry benchmark data (PE, PB averages by sector).

    Uses akshare's stock_industry_pe_ratio_cninfo() (巨潮资讯) which returns
    weighted-average PE, median PE, and arithmetic-average PE for all industries
    classified by CSRC standard.

    Returns:
        Number of industry benchmarks indexed.
    """
    import akshare as ak
    from datetime import datetime
    from services.rag.cache import set_cached_json, get_cached_json

    cache_key = "industry_benchmarks:all"

    # Check cache (7 days)
    cached = get_cached_json(cache_key)
    if cached:
        industries = cached
    else:
        from datetime import datetime, timedelta

        # Try recent dates (today may not be a trading day or data not yet available)
        df = None
        for days_back in range(0, 7):
            try:
                date_str = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")
                df = ak.stock_industry_pe_ratio_cninfo(symbol="证监会行业分类", date=date_str)
                if df is not None and not df.empty:
                    break
            except Exception:
                continue

        if df is None or df.empty:
            return 0

        # Safe value extraction helper
        def _safe_float(val, default=0.0):
            try:
                if val is None:
                    return default
                f = float(val)
                return f if f == f else default  # NaN check
            except (ValueError, TypeError):
                return default

        def _safe_int(val, default=0):
            try:
                if val is None:
                    return default
                f = float(val)
                return int(f) if f == f else default
            except (ValueError, TypeError):
                return default

        industries = []
        for _, row in df.iterrows():
            # Use iloc positional access to avoid encoding issues with column names
            name = str(row.iloc[4]) if len(row) > 4 else ""  # 行业名称
            pe_weighted = _safe_float(row.iloc[9] if len(row) > 9 else 0)  # 静态市盈率-加权平均
            pe_median = _safe_float(row.iloc[10] if len(row) > 10 else 0)  # 静态市盈率-中位数
            pe_avg = _safe_float(row.iloc[11] if len(row) > 11 else 0)    # 静态市盈率-算术平均
            company_count = _safe_int(row.iloc[5] if len(row) > 5 else 0)  # 公司数量
            mcap_total = _safe_float(row.iloc[7] if len(row) > 7 else 0)   # 总市值-静态
            net_profit = _safe_float(row.iloc[8] if len(row) > 8 else 0)   # 净利润-静态

            if not name or name == "nan":
                continue

            # Calculate ROE proxy for the industry: total net profit / total market cap
            roe_proxy = 0.0
            if mcap_total > 0 and net_profit > 0:
                roe_proxy = round(net_profit / mcap_total * 100, 1)

            industries.append({
                "name": name,
                "pe_weighted": pe_weighted,
                "pe_median": pe_median,
                "pe_avg": pe_avg,
                "roe_proxy": roe_proxy,
                "company_count": company_count,
            })

        # Cache for 7 days
        set_cached_json(cache_key, industries, content_type="industry_benchmark", ttl_hours=168)

    # Index each industry as a chunk
    from services.rag.embeddings import encode_single
    from services.rag.vector_store import upsert_chunk, chunk_is_current

    if not _ensure_embedding_ready():
        return 0

    indexed = 0
    for ind in industries:
        chunk_id = f"industry:{ind['name']}"

        if chunk_is_current(chunk_id):
            indexed += 1
            continue

        content = (
            f"行业分类：{ind['name']}\n"
            f"行业加权平均PE(静态)：{ind['pe_weighted']}\n"
            f"行业PE中位数(静态)：{ind['pe_median']}\n"
            f"行业算术平均PE(静态)：{ind['pe_avg']}\n"
            f"行业ROE近似值：{ind['roe_proxy']}%\n"
            f"行业公司数量：{ind['company_count']} 家\n"
        )

        try:
            vec = encode_single(content)
            upsert_chunk(
                chunk_id=chunk_id,
                content=content,
                vector=vec,
                source_type="industry_benchmark",
                industry=ind["name"],
                metadata={
                    "pe_weighted": ind["pe_weighted"],
                    "pe_median": ind["pe_median"],
                    "pe_avg": ind["pe_avg"],
                    "roe_proxy": ind["roe_proxy"],
                    "company_count": ind["company_count"],
                },
                ttl_hours=168,
            )
            indexed += 1
        except Exception:
            continue

    return indexed


def index_knowledge_base(ticker: str) -> int:
    """Index the output of knowledge_base.py for a ticker.

    Uses the existing knowledge_base module to generate rich 8-quarter
    financial data in Markdown format, then chunks and indexes it.

    Args:
        ticker: Full ticker code like "600519.SH"

    Returns:
        Number of chunks indexed.
    """
    from services.knowledge_base import build_knowledge_base
    from services.rag.chunker import chunk_text
    from services.rag.embeddings import encode_single
    from services.rag.vector_store import upsert_chunk, chunk_is_current

    code = ticker.split(".")[0] if "." in ticker else ticker

    try:
        kb_text = build_knowledge_base(ticker)
    except Exception:
        return 0

    if not kb_text:
        return 0

    chunks = chunk_text(
        kb_text,
        strategy="financial_report",
        metadata={"ticker": ticker, "source": "knowledge_base"},
    )

    if not _ensure_embedding_ready():
        return 0

    full_ticker = f"{code}.{'SH' if code.startswith('6') else 'SZ'}"
    indexed = 0

    for i, chunk in enumerate(chunks):
        chunk_id = f"kb_report:{code}:{i}"

        if chunk_is_current(chunk_id):
            indexed += 1
            continue

        try:
            vec = encode_single(chunk["content"])
            upsert_chunk(
                chunk_id=chunk_id,
                content=chunk["content"],
                vector=vec,
                source_type="financial_report",
                ticker=full_ticker,
                metadata={**chunk.get("metadata", {}), "ticker": full_ticker},
                ttl_hours=24,
            )
            indexed += 1
        except Exception:
            continue

    return indexed


def index_announcements(ticker: str, days: int = 90) -> int:
    """Fetch and index recent announcements for a ticker.

    Uses akshare's stock_individual_notice_report() which returns announcement
    titles, dates, types, and URLs from EastMoney.

    Args:
        ticker: Stock code (short form like "600519")
        days: How many days back to fetch

    Returns:
        Number of announcements indexed.
    """
    import akshare as ak
    from datetime import datetime, timedelta
    from services.rag.embeddings import encode_single
    from services.rag.vector_store import upsert_chunk

    code = ticker.split(".")[0] if "." in ticker else ticker
    full_ticker = f"{code}.{'SH' if code.startswith('6') else 'SZ'}"

    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
        df = ak.stock_individual_notice_report(
            security=code, symbol="全部",
            begin_date=start_date, end_date=end_date,
        )
        if df is None or df.empty:
            return 0
    except Exception:
        return 0

    if not _ensure_embedding_ready():
        return 0

    # Take most recent announcements
    if len(df) > 30:
        df = df.head(30)

    indexed = 0
    for _, row in df.iterrows():
        title = str(row.get("公告标题", ""))
        notice_type = str(row.get("公告类型", ""))
        date_val = row.get("公告日期", "")
        url = str(row.get("网址", ""))
        name = str(row.get("名称", ""))

        if not title:
            continue

        date_str = str(date_val)[:10] if date_val else ""
        chunk_id = f"announcement:{code}:{date_str}:{abs(hash(title)) % 100000}"

        content = f"公告标题：{title}\n公告类型：{notice_type}\n公告日期：{date_str}\n公司：{name}"
        if url:
            content += f"\n来源：{url}"

        try:
            vec = encode_single(content)
            upsert_chunk(
                chunk_id=chunk_id,
                content=content,
                vector=vec,
                source_type="announcement",
                ticker=full_ticker,
                metadata={
                    "title": title,
                    "date": date_str,
                    "type": notice_type,
                    "url": url,
                },
                ttl_hours=6,
            )
            indexed += 1
        except Exception:
            continue

    return indexed


# ═══════════════════════════════════════════════
#  Bulk Indexing Utilities
# ═══════════════════════════════════════════════


def ensure_indexed(ticker: str) -> dict:
    """Ensure all knowledge sources for a ticker are indexed.

    Checks which sources are already indexed and fills any gaps.
    Also checks TTL expiration and re-indexes expired data.
    Used as a pre-debate hook to make sure context is available.

    Args:
        ticker: Full ticker or short code

    Returns:
        dict with status for each source type
    """
    from services.rag.vector_store import count_chunks, has_current_chunks, is_expired

    code = ticker.split(".")[0] if "." in ticker else ticker
    full_ticker = f"{code}.{'SH' if code.startswith('6') else 'SZ'}"

    result = {
        "company_profile": False,
        "industry_benchmarks": False,
        "knowledge_base": False,
        "announcements": False,
    }

    # Company profile - check existence and TTL expiration
    if is_expired("company_profile", full_ticker):
        result["company_profile"] = index_company_profile(ticker)
    else:
        result["company_profile"] = has_current_chunks("company_profile", full_ticker)

    # Industry benchmarks - check count and TTL expiration
    if count_chunks("industry_benchmark", current_only=True) == 0 or is_expired("industry_benchmark"):
        n = index_industry_benchmarks()
        result["industry_benchmarks"] = n > 0
    else:
        result["industry_benchmarks"] = has_current_chunks("industry_benchmark")

    # Knowledge base (financial_report) - check existence and TTL expiration
    if is_expired("financial_report", ticker):
        n = index_knowledge_base(ticker)
        result["knowledge_base"] = n > 0
    else:
        result["knowledge_base"] = has_current_chunks("financial_report", full_ticker)

    # Announcements - always re-index (时效性重要)
    result["announcements"] = index_announcements(ticker) > 0

    return result


def bulk_index_all_stocks(limit: int = 0) -> dict:
    """Index company profiles for all A-share stocks in akshare's stock list.

    This is the initial bulk indexing run — typically done once.

    Args:
        limit: Max number of stocks to index (0 = all)

    Returns:
        dict with indexing statistics
    """
    import akshare as ak
    from services.rag.embeddings import is_fitted, fit_vectorizer, encode_single
    from services.rag.chunker import chunk_text
    from services.rag.vector_store import upsert_chunk, get_all_chunk_ids

    try:
        df = ak.stock_info_a_code_name()
    except Exception as e:
        return {"error": str(e), "indexed": 0}

    existing = set(get_all_chunk_ids("company_profile"))
    stocks = [
        (row["code"], row["name"])
        for _, row in df.iterrows()
    ]
    if limit > 0:
        stocks = stocks[:limit]

    # Phase 1: Collect all content without embedding (fast, API-dependent)
    all_contents = []
    stock_map = {}  # chunk_id -> (ticker, industry)

    for code, name in stocks:
        chunk_id = f"company_profile:{code}:0"
        if chunk_id in existing:
            continue

        from services.rag.cache import get_cached_json
        cached = get_cached_json(f"company_profile:{code}")
        if cached and cached.get("content"):
            content = cached["content"]
            industry = cached.get("industry", "")

            chunks = chunk_text(
                content, strategy="company_profile",
                metadata={"ticker": code, "name": name, "industry": industry},
            )
            for i, chunk in enumerate(chunks):
                cid = f"company_profile:{code}:{i}"
                all_contents.append(chunk["content"])
                stock_map[len(all_contents) - 1] = (cid, code, industry, chunk.get("metadata", {}))
                existing.add(cid)

    if not all_contents:
        # Need to fetch profiles first (slow, API calls)
        pass  # Handled in Phase 2 via ensure_indexed per-ticker

    # Phase 2: Validate embedding runtime if needed
    if not is_fitted():
        # Collect diverse sample for fitting
        sample_texts = []
        # Add concept definitions
        for concept in FINANCIAL_CONCEPTS:
            sample_texts.append(
                f"金融概念：{concept['term']}\n{concept['definition']}\n{concept['usage']}"
            )

        # Add whatever contents we have
        sample_texts.extend(all_contents[:1000])

        if sample_texts:
            fit_vectorizer(sample_texts)

    # Phase 3: Embed and store
    if is_fitted():
        for i, content in enumerate(all_contents):
            if i in stock_map:
                cid, code, industry, meta = stock_map[i]
                try:
                    vec = encode_single(content)
                    full_ticker = f"{code}.{'SH' if str(code).startswith('6') else 'SZ'}"
                    upsert_chunk(
                        chunk_id=cid,
                        content=content,
                        vector=vec,
                        source_type="company_profile",
                        ticker=full_ticker,
                        industry=industry,
                        metadata={**meta, "ticker": full_ticker, "industry": industry},
                        ttl_hours=168,
                    )
                except Exception:
                    continue

    return {
        "total_stocks": len(stocks),
        "profiles_indexed": len(all_contents),
        "embedding_ready": is_fitted(),
    }


def is_rag_ready() -> bool:
    """Check if the RAG system is ready for use (BGE-M3 runtime + current concepts indexed)."""
    from services.rag.embeddings import is_fitted
    from services.rag.vector_store import count_chunks

    return is_fitted() and count_chunks("concept_definition", current_only=True) > 0
