#!/usr/bin/env python3
"""
RAG 库定期更新脚本

使用方式：
    python scripts/rag_refresh.py              # 更新所有过期数据
    python scripts/rag_refresh.py --ticker 600519.SH  # 更新指定股票
    python scripts/rag_refresh.py --full       # 全量重建
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.rag.vector_store import delete_expired_chunks, count_chunks
from services.rag.knowledge_index import (
    index_concept_definitions,
    index_industry_benchmarks,
    index_company_profile,
    index_announcements,
)


def refresh_expired():
    """清理过期数据并更新基准数据"""
    print("=== 清理过期数据 ===")
    deleted = delete_expired_chunks()
    print(f"已清理 {deleted} 条过期数据")

    print("\n=== 当前数据状态 ===")
    for source in ["concept_definition", "company_profile", "industry_benchmark", "announcement"]:
        count = count_chunks(source)
        print(f"  {source}: {count} 条")

    # 概念定义如果缺失则重新索引
    if count_chunks("concept_definition") == 0:
        print("\n=== 重新索引概念定义 ===")
        index_concept_definitions()
        print("概念定义已更新")


def refresh_ticker(ticker: str):
    """更新指定股票的相关数据"""
    print(f"=== 更新股票 {ticker} ===")

    print("索引公司概况...")
    index_company_profile(ticker=ticker)

    print("索引公告...")
    index_announcements(ticker=ticker)

    print(f"股票 {ticker} 数据已更新")


def full_rebuild():
    """全量重建所有索引"""
    print("=== 全量重建 RAG 索引 ===")

    print("1. 清理所有数据...")
    from services.rag.vector_store import clear_all_chunks
    clear_all_chunks()

    print("2. 索引概念定义...")
    index_concept_definitions()

    print("3. 索引行业基准...")
    index_industry_benchmarks()

    print("4. 索引公司概况（热门股票）...")
    hot_stocks = ["600519.SH", "000858.SZ", "000001.SZ", "601318.SH"]
    for stock in hot_stocks:
        index_company_profile(ticker=stock)

    print("\n=== 重建完成 ===")
    for source in ["concept_definition", "company_profile", "industry_benchmark"]:
        count = count_chunks(source)
        print(f"  {source}: {count} 条")


def main():
    parser = argparse.ArgumentParser(description="RAG 库更新脚本")
    parser.add_argument("--ticker", type=str, help="更新指定股票")
    parser.add_argument("--full", action="store_true", help="全量重建")

    args = parser.parse_args()

    if args.full:
        full_rebuild()
    elif args.ticker:
        refresh_ticker(args.ticker)
    else:
        refresh_expired()


if __name__ == "__main__":
    main()