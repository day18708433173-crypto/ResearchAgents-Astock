"""事实校验引擎 —— 简化版本（MVP V2）"""

import re


def _extract_number(text: str) -> float | None:
    """从文本中提取数值"""
    text = text.strip()
    # 去除单位
    text = re.sub(r'[万亿%倍点元股]', '', text)
    try:
        return float(text)
    except:
        return None


def verify(rounds: list[dict], data_card: dict) -> dict:
    """简化版事实校验：只统计验证情况"""
    fields = data_card.get("fields", {})
    verified = 0
    unverifiable = 0
    deviations = []

    for r in rounds:
        for role in ("bull", "bear"):
            text = r.get(role, "")
            # 提取数值
            numbers = re.findall(r'(\d+\.?\d*[万亿%倍点元股]*)', text)
            
            for num_str in numbers:
                claim_val = _extract_number(num_str)
                if claim_val is None:
                    continue
                
                # 检查是否匹配数据卡
                matched = False
                for field_name, field in fields.items():
                    if isinstance(field, dict) and field.get("value"):
                        ref_val = _extract_number(str(field["value"]))
                        if ref_val and abs(claim_val - ref_val) / abs(ref_val) < 0.1:
                            verified += 1
                            matched = True
                            break
                
                if not matched:
                    unverifiable += 1

    # 计算准确率
    total = verified + unverifiable
    accuracy = verified / total if total > 0 else 0.5
    
    if accuracy >= 0.8:
        grade = "A"
    elif accuracy >= 0.6:
        grade = "B"
    elif accuracy >= 0.4:
        grade = "C"
    else:
        grade = "D"

    return {
        "verified": verified,
        "unverifiable": unverifiable,
        "accuracy": accuracy,
        "accuracy_grade": grade,
        "deviations": deviations,
        "total_claims": total,
    }