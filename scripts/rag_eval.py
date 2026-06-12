"""
RAG 效果评估脚本

评估维度：
1. 检索质量：命中率、分数分布、时效性
2. 内容质量：检索内容是否相关、是否有价值
3. 业务效果：Agent 是否使用了检索内容

使用方式：
    python scripts/rag_eval.py --ticker 600519.SH
    python scripts/rag_eval.py --full  # 完整评估
"""

import argparse
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
RAG_DB = ROOT / "data" / "rag_vectors.db"


def eval_retrieval_quality():
    """评估检索质量"""
    conn = sqlite3.connect(str(RAG_DB))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    report = {
        "title": "检索质量评估",
        "sections": []
    }
    
    # 1. 数据源覆盖度
    cursor.execute('SELECT source_type, COUNT(*) FROM rag_chunks GROUP BY source_type')
    data_coverage = dict(cursor.fetchall())
    report["sections"].append({
        "name": "数据源覆盖度",
        "data": data_coverage,
        "analysis": _analyze_coverage(data_coverage)
    })
    
    # 2. 检索命中率
    cursor.execute('''
        SELECT source_types, AVG(hit_count) as avg_hits, 
               COUNT(CASE WHEN hit_count=0 THEN 1 END) as zero_hits,
               COUNT(*) as total
        FROM rag_retrieval_log 
        GROUP BY source_types
    ''')
    hit_rate_data = []
    for row in cursor.fetchall():
        sources = json.loads(row['source_types'])
        hit_rate = 1 - (row['zero_hits'] / row['total']) if row['total'] > 0 else 0
        hit_rate_data.append({
            "source": sources[0] if sources else "unknown",
            "avg_hits": round(row['avg_hits'], 2),
            "hit_rate": round(hit_rate, 2),
            "zero_count": row['zero_hits']
        })
    report["sections"].append({
        "name": "检索命中率",
        "data": hit_rate_data,
        "analysis": _analyze_hit_rate(hit_rate_data)
    })
    
    # 3. 相似度分数分布
    cursor.execute('SELECT top_scores FROM rag_retrieval_log ORDER BY id DESC LIMIT 100')
    all_scores = []
    for row in cursor.fetchall():
        scores = json.loads(row['top_scores'])
        all_scores.extend(scores)
    
    if all_scores:
        score_dist = {
            "avg": round(sum(all_scores)/len(all_scores), 3),
            "max": round(max(all_scores), 3),
            "min": round(min(all_scores), 3),
            "high_>0.5": len([s for s in all_scores if s > 0.5]),
            "medium_0.2-0.5": len([s for s in all_scores if 0.2 <= s <= 0.5]),
            "low_<0.2": len([s for s in all_scores if s < 0.2])
        }
        report["sections"].append({
            "name": "相似度分数分布",
            "data": score_dist,
            "analysis": _analyze_scores(score_dist)
        })
    
    # 4. 数据时效性
    cursor.execute('''
        SELECT source_type, MAX(generated_at) as latest, MIN(generated_at) as earliest, ttl_hours
        FROM rag_chunks 
        GROUP BY source_type
    ''')
    freshness_data = []
    now = datetime.now()
    for row in cursor.fetchall():
        if row['latest']:
            latest = datetime.fromisoformat(row['latest'][:19])
            age_hours = (now - latest).total_seconds() / 3600
            ttl = row['ttl_hours'] or 0
            freshness_data.append({
                "source": row['source_type'],
                "latest": row['latest'][:19],
                "age_hours": round(age_hours, 1),
                "ttl_hours": ttl,
                "status": "过期" if ttl > 0 and age_hours > ttl else "新鲜" if ttl > 0 else "永久"
            })
    report["sections"].append({
        "name": "数据时效性",
        "data": freshness_data,
        "analysis": _analyze_freshness(freshness_data)
    })
    
    conn.close()
    return report


def eval_content_quality(ticker: str):
    """评估内容质量 - 检查检索内容是否相关"""
    import sys
    sys.path.insert(0, str(ROOT))
    from services.rag.context_builder import enrich_data_card
    
    report = {
        "title": f"内容质量评估 - {ticker}",
        "ticker": ticker
    }
    
    # 模拟一个空数据卡来触发 RAG 检索
    fake_data_card = {"估值数据": {}, "财务数据": {}, "预期数据": {}}
    
    try:
        enriched = enrich_data_card(ticker, fake_data_card)
        
        # 评估检索结果
        content_analysis = {
            "company_profile": {
                "found": enriched["status"]["company_profile"],
                "length": len(enriched["company_profile"]),
                "sample": enriched["company_profile"][:100] if enriched["company_profile"] else "无"
            },
            "industry_profile": {
                "found": enriched["status"]["industry_profile"],
                "length": len(enriched["industry_profile"]),
                "sample": enriched["industry_profile"][:100] if enriched["industry_profile"] else "无"
            },
            "announcements": {
                "found": enriched["status"]["announcements"],
                "count": len(enriched["recent_announcements"]),
                "titles": [a.get("title", "")[:50] for a in enriched["recent_announcements"][:3]]
            }
        }
        
        report["content_analysis"] = content_analysis
        report["overall_score"] = sum([
            1 if content_analysis["company_profile"]["found"] else 0,
            1 if content_analysis["industry_profile"]["found"] else 0,
            1 if content_analysis["announcements"]["found"] else 0
        ]) / 3
        
    except Exception as e:
        report["error"] = str(e)
        report["overall_score"] = 0
    
    return report


def _analyze_coverage(data):
    """分析数据覆盖度"""
    issues = []
    if data.get("company_profile", 0) < 10:
        issues.append("公司概况数据不足，建议补充更多股票的公司资料")
    if data.get("industry_benchmark", 0) < 50:
        issues.append("行业基准数据不足，建议补充更多行业的基准数据")
    return issues if issues else ["数据覆盖度良好"]


def _analyze_hit_rate(data):
    """分析命中率"""
    issues = []
    for d in data:
        if d["hit_rate"] < 0.8:
            issues.append(f"{d['source']} 命中率偏低({d['hit_rate']:.0%})，有{d['zero_count']}次未命中")
    return issues if issues else ["检索命中率良好"]


def _analyze_scores(data):
    """分析相似度分数"""
    issues = []
    if data["avg"] < 0.3:
        issues.append("平均相似度过低，检索精度可能有问题，建议优化查询词或向量模型")
    if data["high_>0.5"] == 0:
        issues.append("没有高分检索结果，可能索引内容与查询不够匹配")
    return issues if issues else ["相似度分数分布正常"]


def _analyze_freshness(data):
    """分析数据时效性"""
    issues = []
    for d in data:
        if d["status"] == "过期":
            issues.append(f"{d['source']} 已过期(age={d['age_hours']}h > ttl={d['ttl_hours']}h)，需要更新")
    return issues if issues else ["数据时效性良好"]


def print_report(report):
    """打印评估报告"""
    print("\n" + "="*60)
    print(f"📊 {report['title']}")
    print("="*60)
    
    if "overall_score" in report:
        score = report["overall_score"]
        grade = "优秀" if score >= 0.8 else "良好" if score >= 0.6 else "待改进" if score >= 0.4 else "不合格"
        print(f"\n综合评分: {score:.0%} ({grade})")
    
    for section in report.get("sections", []):
        print(f"\n### {section['name']}")
        print("-"*40)
        if isinstance(section['data'], dict):
            for k, v in section['data'].items():
                print(f"  {k}: {v}")
        elif isinstance(section['data'], list):
            for item in section['data']:
                print(f"  {item}")
        print(f"\n  💡 分析: {section['analysis']}")
    
    if "content_analysis" in report:
        print(f"\n### 内容质量详情")
        print("-"*40)
        for source, info in report["content_analysis"].items():
            status = "✅" if info["found"] else "❌"
            print(f"  {status} {source}: 长度={info.get('length', 0)}")
            if "sample" in info:
                print(f"      示例: {info['sample']}")
    
    print("\n" + "="*60)


def main():
    parser = argparse.ArgumentParser(description="RAG 效果评估")
    parser.add_argument("--ticker", help="评估指定股票的 RAG 内容质量")
    parser.add_argument("--full", action="store_true", help="完整评估（检索质量 + 内容质量）")
    args = parser.parse_args()
    
    if args.full or args.ticker:
        # 检索质量评估
        retrieval_report = eval_retrieval_quality()
        print_report(retrieval_report)
        
        # 内容质量评估
        if args.ticker:
            try:
                content_report = eval_content_quality(args.ticker)
                print_report(content_report)
            except ImportError as e:
                print(f"⚠️ 内容质量评估跳过（缺少依赖: {e}）")
                print("💡 可在辩论页面测试内容质量")
    else:
        # 默认只做检索质量评估
        retrieval_report = eval_retrieval_quality()
        print_report(retrieval_report)


if __name__ == "__main__":
    main()