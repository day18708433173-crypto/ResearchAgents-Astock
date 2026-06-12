"""镜衡 Backend API — FastAPI 入口

启动: uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload

路由按职责拆分在 backend/routers/ 下：
  stock.py        — /api/health、/api/rag/stats、/api/stock/search
  dossier.py      — /api/dossier/*、/api/export/dossier/*
  strategy.py     — /api/strategy/*
  transaction.py  — /api/transaction/*
  debate.py       — /api/debate/*（含 SSE 流式辩论、策略教练、金融科普）
"""

import os
import sys
import logging
from pathlib import Path

# ── 日志配置 ──
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ── 环境配置 ──
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(k, None)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.db_init import init_database

# ── 初始化数据库 ──
init_database()

app = FastAPI(
    title="镜衡 API V2",
    description="24小时投资策略伴侣 · MVP P0",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup_init():
    """启动时初始化 RAG（BGE-M3 embedding + 金融概念/行业对标索引）。"""
    try:
        from services.rag.startup import init_rag
        status = init_rag(verbose=True)
        if status.get("ready"):
            logger.info("[RAG] System ready: %s", status)
        else:
            logger.warning("[RAG] System not fully ready: %s", status)
    except Exception as e:
        logger.warning("[RAG] Startup init failed (non-fatal): %s", e)


# ── 路由注册（注意：各 router 内部已保证静态路由在动态路由之前）──
from backend.routers import stock, dossier, strategy, transaction, debate

app.include_router(stock.router)
app.include_router(dossier.router)
app.include_router(strategy.router)
app.include_router(transaction.router)
app.include_router(debate.router)
