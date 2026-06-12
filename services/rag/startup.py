"""RAG system startup initialization.

Called once when the app starts. Ensures:
- Vector store tables exist
- BGE-M3 embedding runtime is available
- Core knowledge sources are pre-indexed (concepts, industries)
- Expired chunks are cleaned up

All operations are idempotent — safe to call on every app restart.
"""

import sys
from pathlib import Path


def init_rag(verbose: bool = True) -> dict:
    """Initialize the RAG system on app startup.

    Safe to call repeatedly — all steps are idempotent.

    Returns:
        dict with initialization status for each component
    """
    status = {
        "vector_store": False,
        "embedding_model": False,
        "concepts": 0,
        "industries": 0,
        "expired_cleaned": 0,
        "ready": False,
        "warnings": [],
    }

    # ── 1. Vector store tables ──
    try:
        from services.rag.vector_store import init_vector_store
        init_vector_store()
        status["vector_store"] = True
    except Exception as e:
        status["warnings"].append(f"vector_store init failed: {e}")
        return status  # Can't proceed without vector store

    # ── 2. Validate embedding model runtime ──
    from services.rag.embeddings import is_fitted, fit_vectorizer
    if not is_fitted():
        try:
            fit_vectorizer([])
            status["embedding_model"] = True
            if verbose:
                print("[RAG] BGE-M3 embedding model loaded")
        except Exception as e:
            status["warnings"].append(f"BGE-M3 load failed: {e}")
            return status
    else:
        status["embedding_model"] = True

    # ── 3. Pre-index concept definitions (idempotent, static) ──
    try:
        from services.rag.knowledge_index import index_concept_definitions
        n = index_concept_definitions()
        status["concepts"] = n
        if verbose:
            print(f"[RAG] {n} concept definitions indexed")
    except Exception as e:
        status["warnings"].append(f"concept indexing failed: {e}")

    # ── 4. Pre-index industry benchmarks (idempotent, 7-day TTL) ──
    try:
        from services.rag.vector_store import count_chunks
        if count_chunks("industry_benchmark", current_only=True) == 0:
            from services.rag.knowledge_index import index_industry_benchmarks
            n = index_industry_benchmarks()
            status["industries"] = n
            if verbose:
                print(f"[RAG] {n} industry benchmarks indexed")
        else:
            # Industries already indexed — check if they're expired
            from services.rag.vector_store import delete_expired_chunks
            cleaned = delete_expired_chunks()
            status["expired_cleaned"] = cleaned
            status["industries"] = count_chunks("industry_benchmark", current_only=True)
            if verbose and cleaned > 0:
                print(f"[RAG] {cleaned} expired chunks cleaned")
    except Exception as e:
        status["warnings"].append(f"industry indexing failed: {e}")

    # ── 5. Cleanup expired chunks across all sources ──
    if status["expired_cleaned"] == 0:
        try:
            from services.rag.vector_store import delete_expired_chunks
            cleaned = delete_expired_chunks()
            status["expired_cleaned"] = cleaned
        except Exception:
            pass

    # ── 6. Final readiness check ──
    from services.rag.knowledge_index import is_rag_ready
    status["ready"] = is_rag_ready()

    if verbose:
        if status["ready"]:
            from services.rag.vector_store import count_chunks
            total = count_chunks(current_only=True)
            print(f"[RAG] System ready — {total} current BGE-M3 chunks indexed")
        else:
            print("[RAG] System not fully ready — will index on first debate")

    return status


def _build_startup_corpus() -> list[str]:
    """Return representative financial text kept for legacy tooling.

    BGE-M3 no longer needs corpus fitting, but some maintenance scripts still
    call this helper when constructing sample payloads.
    """
    texts = []

    # Concept definitions
    try:
        from services.rag.knowledge_index import FINANCIAL_CONCEPTS
        for concept in FINANCIAL_CONCEPTS:
            texts.append(
                f"金融概念：{concept['term']} "
                f"{concept['definition']} "
                f"{concept['usage']} "
                f"{' '.join(concept['related_terms'])}"
            )
    except Exception:
        pass

    # Industry domain samples (ensure coverage across Shenwan sectors)
    domain_samples = [
        # 金融
        "银行 不良贷款率 资本充足率 净息差 拨备覆盖率 对公贷款 零售金融 中间业务收入",
        "券商 保险 信托 基金 资产管理 财富管理 注册制 做市商",
        # 消费
        "白酒 啤酒 乳制品 调味品 食品饮料 品牌壁垒 高端化 渠道下沉 经销商体系",
        "家电 汽车 服装 零售 电商 直播带货 消费升级 下沉市场",
        # 科技
        "半导体 芯片设计 晶圆制造 封装测试 EDA IP授权 光刻机 先进制程 进口替代",
        "消费电子 通信 5G 光模块 服务器 云计算 数据中心 AI大模型",
        "软件 SaaS 信息安全 信创 国产替代 操作系统 数据库",
        # 医药
        "创新药 仿制药 生物药 医疗器械 CXO 临床试验 一致性评价 集采 医保谈判",
        # 制造
        "新能源汽车 动力电池 光伏 风电 储能 充电桩 碳中和 碳交易 绿色金融",
        "工程机械 工业自动化 机器人 数控机床 工业互联网 智能制造",
        "军工 航天 航空发动机 无人机 卫星导航 军民融合",
        # 周期
        "钢铁 煤炭 有色金属 稀土 石油化工 基础化工 新材料 钛白粉 锂电池",
        "水泥 玻璃 玻纤 建材 基建 REITs 专项债 新基建",
        # 地产
        "房地产 物业管理 商业地产 长租公寓 保障房 城市更新 旧改",
        # 公用事业
        "电力 水务 燃气 环保 垃圾焚烧 污水处理 海绵城市",
        # 农林牧渔
        "种业 养殖 饲料 农药 化肥 转基因 农产品加工",
        # 交通运输
        "航空 机场 港口 航运 铁路 物流 快递 供应链",
        # 传媒
        "游戏 出版 影视 广告 在线教育 知识付费 短视频 MCN",
    ]

    texts.extend(domain_samples)

    # Some company-specific samples for ticker-level vocabulary
    company_samples = [
        "600519 贵州茅台 白酒 茅台酒 品牌护城河 高毛利率 高净利率 预收账款 出厂价 一批价",
        "000858 五粮液 浓香型 品牌力 渠道改革 数字化营销 经典五粮液",
        "300750 宁德时代 动力电池 储能系统 全球市占率 客户结构 产能扩张",
        "600036 招商银行 零售之王 AUM 财富管理 私行 对公业务 资产质量",
    ]
    texts.extend(company_samples)

    return texts
