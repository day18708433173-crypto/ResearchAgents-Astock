"""信源自动标注 —— 简化版本（MVP V2）

标签类型：
- 已验证数据：数值与数据卡字段匹配
- 逻辑推理：推理型论点
- 待核实：无法验证的声明
"""

import re


def tag_output(text: str, data_card_fields: dict, rag_context: dict = None) -> list[dict]:
    """简化版标注：只检查是否包含数值，是否匹配数据卡"""
    results = []
    
    # 提取数值
    numbers = re.findall(r'(\d+\.?\d*[万亿%]?)', text)
    
    for num in numbers:
        # 检查是否在数据卡中
        matched = False
        for field_name, field_data in data_card_fields.items():
            if isinstance(field_data, dict):
                value = field_data.get("value")
                if value and str(value) in num or num in str(value):
                    matched = True
                    results.append({
                        "text": num,
                        "tag": "已验证数据",
                        "source": field_name,
                    })
                    break
        
        if not matched:
            results.append({
                "text": num,
                "tag": "待核实",
                "source": None,
            })
    
    # 检查推理标记
    inference_markers = ["我的判断是", "我认为", "推测", "估计"]
    for marker in inference_markers:
        if marker in text:
            results.append({
                "text": marker,
                "tag": "逻辑推理",
                "source": None,
            })
    
    return results


def tag_outputs_batch(bull_text: str, bear_text: str, fields: dict, rag_context: dict = None) -> tuple:
    """批量标注多空双方输出"""
    return (
        tag_output(bull_text, fields, rag_context),
        tag_output(bear_text, fields, rag_context),
    )