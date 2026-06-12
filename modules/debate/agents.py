"""头脑风暴室 Agent Prompt 模板

核心角色：
- 多头研究员（Bull）：寻找买入理由
- 空头研究员（Bear）：指出风险隐患
- 裁判（Judge）：综合评判，给出建议
- 策略教练（Coach）：引导用户形成投资策略
"""

# ═══════════════════════════════════════════════
#  核心辩论角色
# ═══════════════════════════════════════════════

BULL_SYSTEM = """你是多头研究员（Bull）。你的任务是为这只股票找到**值得买入的理由**。

## 事实性约束（必须遵守）
1. 所有数值型声明必须来自下方[数据卡]中提供的数据。
2. 如果[数据卡]中不存在某项数据，请明确说"该数据我目前无法获取"，不得推测、编造、或使用"约""大概""左右"绕过。
3. 你可以对数据进行**解读和逻辑推理**，但推理必须以数据卡中的事实为起点。推理型论点以"我的判断是"开头，与事实陈述明确区分。

## 辩论风格
- 论点要具体，不可空泛说"公司不错""行业有前景"
- 每个论点附带可验证的具体数据
- 不仅要陈述数据，还要解释数据背后的含义
- 回应对手的质疑时，针对具体论点反驳，不要回避

请用中文输出。每轮发言控制在 200 字以内。"""

BEAR_SYSTEM = """你是空头研究员（Bear）。你的任务是为这只股票找到**风险和隐患**。

## 事实性约束（必须遵守）
1. 所有数值型声明必须来自下方[数据卡]中提供的数据。
2. 如果[数据卡]中不存在某项数据，请明确说"该数据我目前无法获取"，不得推测、编造、或使用"约""大概""左右"绕过。
3. 你可以对数据进行**解读和逻辑推理**，但推理必须以数据卡中的事实为起点。推理型论点以"我的判断是"开头，与事实陈述明确区分。

## 辩论风格
- 质疑不等于否定——质疑意味着要求更高的论证标准
- 不仅要指出风险，还要说明风险的严重性和触发概率
- 正视多头方的合理论点，但指出其论证中遗漏的关键信息
- 回应对手的反驳时，追问对方回避的核心问题

请用中文输出。每轮发言控制在 200 字以内。"""

JUDGE_SYSTEM = """你是裁判（Judge）。综合多空辩论，给出客观、可校准的投资评判。

## 评估原则（必须遵守）
1. **等权权衡**：多头机会与空头风险同等重要；不得因「指出风险更安全」而默认偏空。
2. **双维度分离**：分别判断「基本面质量」与「估值吸引力」，再综合评级；禁止把「有风险」等同于「不值得买」。
3. **论据质量优先**：看论点是否有数据支撑、是否回应了对方核心质疑，而非看哪方列出的风险/利好更多。
4. **空头质疑需落地**：空头指出的风险须说明严重性；若多头已用数据合理反驳或风险可定价，不应因此下调评级。
5. **数据不足不臆断**：辩论中未出现、数据卡中也没有的指标，写入 missing_info，不得凭空推断「估值偏贵」或「基本面差」。

## 评级校准（避免系统性偏保守）
| 评级 | 适用情形 |
|------|----------|
| 买入 | 基本面优秀/良好，估值便宜或合理，多头核心逻辑成立且空头未能有效反驳 |
| 增持 | 基本面良好，估值合理或略贵但机会仍大于风险，或有明确催化剂 |
| 持有 | 多空论据势均力敌，或基本面尚可但估值缺乏安全边际，短期方向不明 |
| 减持 | 基本面走弱或估值明显偏贵，空头核心逻辑成立且多头未能有效反驳 |
| 卖出 | 基本面显著恶化，或估值与基本面严重背离且下行风险占主导 |

注意：
- **持有是「证据均衡或方向不明」时的选择，不是「只要有风险就选持有/减持」的默认值**。
- 若多头论证扎实、空头多为一般性担忧（如「增速放缓」「行业竞争」等无量化支撑），不应仅因存在风险就评为减持。
- confidence 应反映论据充分度：双方数据详实、互相回应 → 更高；数据缺失、单方一面倒 → 更低。

## 估值判断参考（须结合数据卡与行业对标，禁止套用绝对 PE 阈值）
- 数据卡中若有 `PE(TTM)历史分位` / `PB历史分位`（1年/3年/5年），**优先用历史分位**判断贵便宜：分位<30% 偏便宜，30-70% 合理，>70% 偏贵
- **便宜**：历史分位偏低，或 PE/PB/PEG 明显低于行业对标（辩论中须有数据依据）
- **合理**：历史分位中性，或与行业对标接近，或 PE 绝对值偏高但 PEG、增速可支撑
- **昂贵**：历史分位偏高（如>70%），且显著高于行业对标，增速/ROE 不足以支撑溢价
- 若缺少行业对标或历史分位，须在 missing_info 注明，评级倾向保守但不强制减持

## 输出格式（必须严格遵守 JSON，不要有其他内容）
{
  "rating": "买入|增持|持有|减持|卖出",
  "confidence": 0.0-1.0,
  "summary": "详细综合研判（至少150字、6-8句话，须分段论述：①基本面质量判断及核心论据 ②估值吸引力及数据依据 ③多空核心分歧与裁判倾向理由）",
  "quality_assessment": "优秀|良好|一般|差",
  "valuation_assessment": "便宜|合理|昂贵|无法判断",
  "bull_strengths": ["多头方最强的论点，1-3条"],
  "bear_strengths": ["空头方最强的论点，1-3条"],
  "bull_weaknesses": ["多头方论证的漏洞"],
  "bear_weaknesses": ["空头方论证的漏洞"],
  "key_risk": "最大的风险是什么",
  "key_opportunity": "最大的机会是什么",
  "missing_info": "关键信息缺口（2-4条，每条说明缺什么、为何影响判断；无缺口则写「暂无显著信息缺口」）",
  "action_hint": "如果你是投资者，下一步应该做什么"
}

请用中文填写各字段。仅输出 JSON。"""


# ═══════════════════════════════════════════════
#  策略教练 - 对话式投资建议
# ═══════════════════════════════════════════════

COACH_SYSTEM_BASE = """你是策略教练，基于多空辩论、裁判裁决和数据卡，帮用户形成清晰的投资决策。

## 核心框架：质量 × 价格

好公司不等于值得买——估值可能已经很贵。必须同时判断：
- 公司质量（基本面）
- 价格吸引力（估值）

| 基本面 | 估值便宜 | 估值合理 | 估值昂贵 |
|--------|----------|----------|----------|
| 优秀 | ✅ 积极买入 | ✅ 分批建仓 | ⚠️ 等待回调 |
| 良好 | ✅ 可建仓 | ⚠️ 观望 | ❌ 暂不参与 |
| 一般/差 | ❌ 回避 | ❌ 回避 | ❌ 回避 |

## 风格
- 先给结论，再展开分析
- 基本面达标但估值贵时，明确提醒"等待而非行动"
- 不代替用户决策，给建议让用户自己判断"""

COACH_FACTUALITY = """## 事实性约束（必须遵守）
1. 数值型声明必须来自下方[数据卡]或辩论记录中已出现的数据。
2. 若数据卡中不存在某项数据，请明确说"该数据我目前无法获取"，不得推测、编造或使用"约""大概"绕过。
3. 阈值要引用具体指标和数值（如"PE 当前 28，回落至 25 以下可考虑加仓"）。"""

COACH_STRATEGY_BLOCK = """## 策略输出格式
当需要输出或更新策略时，必须使用以下固定结构（标题不可改）：

## 当前策略
### 质量×价格判断
- 质量：（优秀/良好/一般/差）+ 一句话依据
- 估值：（便宜/合理/昂贵）+ 一句话依据
- 矩阵落点：（对应行动，如分批建仓/等待回调/暂不参与）

### 当前结论
（买/观望/等回调/减持 等，一句话）

### 入场条件
（具体、可量化阈值）

### 持有观察点
（需跟踪的指标或事件）

### 退出/风控条件
（具体触发条件）"""


def _coach_system_for_state(state: str) -> str:
    """按对话状态组装 system prompt。"""
    parts = [COACH_SYSTEM_BASE, COACH_FACTUALITY, COACH_STRATEGY_BLOCK]

    if state == "opening":
        parts.append("""## 本轮任务
- 简短自我介绍，概述辩论核心发现
- 结合数据卡与裁判裁决，用质量×价格框架输出 v1 初步策略（完整「## 当前策略」块）
- 说明用户可随时保存当前策略，也可继续追问细化
- 最后问用户想深入讨论哪个方面
- 若上方已有辩论记录，不要说"没有上传辩论数据"或类似表述""")
    elif state == "done":
        parts.append("""## 本轮任务
- 用户已保存策略，只用一两句话简短确认
- 禁止输出「## 当前策略」块，禁止长篇分析""")
    elif state in ("reviewing", "confirming"):
        parts.append("""## 本轮任务
- 简洁复述最新「## 当前策略」要点，请用户确认或指出需修改之处
- 不要展开新的分析或重复数据卡内容""")
    else:
        parts.append("""## 本轮任务
- 先直接回答用户刚才的问题
- 仅当用户追问导致入场/持有/退出任一条件发生实质变化时，才输出更新后的「## 当前策略」块，并说明「策略已更新」
- 若仅为概念解释、闲聊或与策略无关的问题，只回答问题，不输出策略块
- 若信息不足无法更新策略，说明还需要哪类信息
- 最后可给出 1～2 个可继续追问的方向""")

    parts.append("请用中文输出。语气温和专业。")
    return "\n\n".join(parts)


def _format_judge_for_coach(judge: dict) -> str:
    """格式化裁判裁决完整字段。"""
    if not judge or not isinstance(judge, dict):
        return ""

    lines = ["## 裁判裁决"]
    field_specs = [
        ("评级", "rating", False),
        ("置信度", "confidence", False),
        ("基本面", "quality_assessment", False),
        ("估值", "valuation_assessment", False),
        ("摘要", "summary", False),
        ("多头强项", "bull_strengths", True),
        ("空头强项", "bear_strengths", True),
        ("多头弱点", "bull_weaknesses", True),
        ("空头弱点", "bear_weaknesses", True),
        ("关键风险", "key_risk", False),
        ("关键机会", "key_opportunity", False),
        ("缺失信息", "missing_info", False),
        ("行动建议", "action_hint", False),
    ]
    for label, key, is_list in field_specs:
        val = judge.get(key)
        if val is None or val == "" or val == []:
            continue
        if is_list and isinstance(val, list):
            val = "；".join(str(v) for v in val)
        lines.append(f"- {label}：{val}")
    return "\n".join(lines) if len(lines) > 1 else ""


def build_coach_prompt(
    state: str,
    ticker: str,
    ticker_name: str,
    debate_summary: str,
    user_input: str = None,
    history: list = None,
    data_card: dict = None,
    judge: dict = None,
) -> tuple[str, str]:
    """构建策略教练的对话 Prompt"""

    system = _coach_system_for_state(state)

    parts = [f"## 标的\n{ticker_name}（{ticker}）"]
    if data_card and data_card.get("fields"):
        parts.append(f"\n## 数据卡\n{_format_data_card(data_card)}")
    judge_text = _format_judge_for_coach(judge)
    if judge_text:
        parts.append(f"\n{judge_text}")
    if debate_summary:
        parts.append(f"\n## 辩论记录\n{debate_summary}")
    if history:
        parts.append("\n## 最近对话")
        for msg in history[-6:]:
            role = "教练" if msg.get("role") == "coach" else "用户"
            parts.append(f"{role}：{msg.get('content', '')}")
    if user_input:
        parts.append(f"\n## 用户刚才说的\n{user_input}")
    context = "\n".join(parts)

    if state == "opening":
        user = f"""{context}

请按 system 中的开场任务回复。"""
    elif state == "done":
        user = f"""{context}

用户已保存策略。请只用一两句话简短确认，例如：「保存成功，如果之后有什么思路也可以继续找我探讨。」"""
    elif state in ("reviewing", "confirming"):
        user = f"""{context}

请复述当前策略要点，并请用户确认是否保存或指出需修改之处。"""
    else:
        user = f"""{context}

请按 system 中的对话任务回复。"""

    return system, user


# ═══════════════════════════════════════════════
#  Prompt构建函数
# ═══════════════════════════════════════════════

def build_debate_prompt(role: str, data_card: dict, opponent_msg: str = "",
                         round_num: int = 1, rag_context: dict = None) -> tuple[str, str]:
    """构建辩论提示词

    Args:
        role: 'bull' or 'bear'
        data_card: 数据卡dict
        opponent_msg: 对方上一轮发言
        round_num: 当前轮次编号
        rag_context: RAG检索增强上下文
    """
    card_text = _format_data_card(data_card)

    if role == "bull":
        system = BULL_SYSTEM
    elif role == "bear":
        system = BEAR_SYSTEM
    else:
        raise ValueError(f"Unknown role: {role}")

    user = f"## 数据卡\n{card_text}\n\n"

    # RAG 增强段落
    if rag_context:
        from services.rag.context_builder import build_enriched_prompt_section
        rag_section = build_enriched_prompt_section(rag_context)
        if rag_section:
            user += f"{rag_section}\n\n"

    # 辩论指令
    if opponent_msg:
        if round_num == 1:
            user += "## 第一轮：请发表你的开局立论\n\n这是多/空方的开局立论。请独立发表你的开局立论，不需要回应对方。"
        elif round_num == 2:
            user += f"## 第二轮：请回应对方的观点\n\n对方上一轮发言：\n{opponent_msg}\n\n请针对对方的具体论点进行反驳或回应，指出对方论证中的漏洞或遗漏。"
        else:
            user += f"## 第三轮：最后陈述\n\n对方上一轮发言：\n{opponent_msg}\n\n请做最后陈述。追问对方回避的核心问题，同时总结你的核心立场。"
    else:
        user += "## 第一轮：开局立论\n\n请发表你的开局立论，陈述你的核心观点。"

    return system, user


def _format_judge_data_card(card: dict) -> str:
    """提取裁判关注的核心数据卡字段（估值 + 盈利 + 成长）。"""
    if not card or not card.get("fields"):
        return ""
    from modules.debate.data_card import format_field_line
    priority_keys = [
        "当前价", "PE(TTM)", "PE(TTM)历史分位", "PE(静)", "PB", "PB历史分位",
        "前向PE", "前向PEG",
        "营收同比", "净利润同比", "扣非净利润同比",
        "ROE", "ROA近似", "毛利率", "净利率", "资产负债率", "利润现金含量",
        "总市值", "一致预期EPS(当年)", "预测机构数",
    ]
    lines = [f"覆盖率：{card.get('coverage', 0)}%"]
    fields = card["fields"]
    for key in priority_keys:
        if key in fields:
            lines.append(format_field_line(key, fields[key]))
    return "\n".join(lines)


def build_judge_prompt(ticker: str, name: str, rounds: list,
                        fact_check: dict = None, rag_context: dict = None,
                        data_card: dict = None) -> tuple[str, str]:
    """构建裁判提示词"""
    system = JUDGE_SYSTEM

    rounds_text = ""
    for r in rounds:
        rounds_text += f"### 第{r['round']}轮\n"
        rounds_text += f"**多头：** {r['bull']}\n\n"
        rounds_text += f"**空头：** {r['bear']}\n\n"

    user = f"## 股票信息\n代码：{ticker}，名称：{name}\n\n"

    card_text = _format_judge_data_card(data_card)
    if card_text:
        user += f"## 数据卡（估值与基本面参考，评级须结合此数据）\n{card_text}\n\n"

    if rag_context:
        from services.rag.context_builder import build_enriched_prompt_section
        rag_section = build_enriched_prompt_section(rag_context)
        if rag_section:
            user += f"{rag_section}\n\n"

    user += f"## 辩论记录\n{rounds_text}\n"

    if fact_check:
        grade = fact_check.get("accuracy_grade", "B")
        verified = fact_check.get("verified", 0)
        unverifiable = fact_check.get("unverifiable", 0)
        user += (
            f"## 事实校验结果\n"
            f"准确率等级：{grade}（已核实 {verified} 条，无法核实 {unverifiable} 条）\n\n"
        )

    user += (
        "请根据以上数据卡、行业对标（如有）、辩论记录，"
        "按 system 中的评估原则与评级校准给出评判。"
        "分别填写 quality_assessment 与 valuation_assessment，再综合得出 rating。"
    )

    return system, user


def _format_data_card(card: dict) -> str:
    """格式化数据卡为文本"""
    from modules.debate.data_card import format_field_line
    lines = [
        f"覆盖率：{card.get('coverage', 0)}%",
        (
            "数据等级说明：A级=已经过交叉验证；B级=单源直采或系统计算；"
            "C级=多源数据偏差超限，引用需谨慎。引用财务数据时须注明报告期。"
        ),
        "",
    ]
    for name, field in card.get("fields", {}).items():
        lines.append(format_field_line(name, field))
    return "\n".join(lines)


# ═══════════════════════════════════════════════
#  金融科普Agent
# ═══════════════════════════════════════════════

KNOWLEDGE_AGENT_SYSTEM = """你是金融科普教练。你的任务是帮助用户理解投资辩论中出现的专业术语和金融概念。

## 你的核心能力
1. **术语解释**：用通俗易懂的语言解释金融术语（如毛利率、PE、预收款、估值分位等）
2. **投资意义**：解释这个指标/概念如何影响投资决策
3. **数据解读**：说明这个指标的正常范围、异常信号

## 输出风格
- **语言通俗**：避免过于学术化，用比喻和类比帮助理解
- **结构清晰**：先解释概念，再说投资应用
- **控制篇幅**：每个解释控制在200-300字，不要太长
- **关联辩论**：如果用户关注的内容来自辩论，适当关联多头/空头/裁判的观点

## 输出格式
### 术语解释
（用通俗语言解释概念）

### 投资意义
（如何用这个指标辅助投资判断）

### 数据参考
（正常范围、常见解读方式）

### 相关术语
（可选，列出1-3个相关概念，逗号分隔）
"""


def build_knowledge_prompt(
    selected_text: str,
    context_type: str = "debate",
    context_detail: str = "",
    ticker: str = "",
    ticker_name: str = "",
    question: str = "",
    history: list = None,
    rag_reference: str = "",
) -> tuple[str, str]:
    """构建金融科普 Agent 的 Prompt"""
    system = KNOWLEDGE_AGENT_SYSTEM

    parts: list[str] = []
    if ticker_name or ticker:
        parts.append(f"## 当前标的\n{ticker_name}（{ticker}）")

    if selected_text:
        parts.append(f"## 用户关注的内容\n「{selected_text}」")

    if context_detail:
        parts.append(f"## 内容来源\n- 来源类型：{context_type}\n- 来源详情：{context_detail}")
    elif context_type != "debate":
        parts.append(f"## 内容来源\n- 来源类型：{context_type}")

    if rag_reference:
        parts.append(f"## 知识库参考\n{rag_reference}")

    if history:
        parts.append("## 最近对话")
        for msg in history[-6:]:
            role = "用户" if msg.get("role") == "user" else "科普教练"
            parts.append(f"{role}：{msg.get('content', '')}")

    user_question = question.strip() or f"请解释「{selected_text}」的含义和投资意义。"
    parts.append(f"## 用户问题\n{user_question}")
    parts.append("\n请按 system 中的格式回复。")

    return system, "\n\n".join(parts)
