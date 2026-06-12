# 深色科技金融风

## 类型
金融科技、投资顾问、AI投资教练。

## 设计关键词
可信、安全、理性、数据驱动、精密、专业、科技感。

## 色彩（深色主题）
- 背景：#0b0f14（深蓝黑）
- 背景2：#101620（次背景）
- Surface：rgba(17, 22, 34, 0.92)（卡片背景，带 backdrop-blur）
- 文本：#eef2ff（浅白）
- 次文本：#95a3bc（灰蓝）
- 弱文本：#5c6a82（更暗灰蓝）
- 强调色（青）：#63e6d0（多头/机会/accent）
- 强调色2（蓝）：#7cb8ff（信息/info）
- 暖色（金）：#f5c451（评级/警示/warning）
- 危险色：#ff7a7a（空头/风险/danger）

## 边框
- 边框：rgba(255, 255, 255, 0.08)
- 边框强：rgba(255, 255, 255, 0.14)
- 边框强调：rgba(99, 230, 208, 0.2)

## 阴影
- sm: 0 1px 2px rgba(0,0,0,0.3)
- md: 0 4px 12px rgba(0,0,0,0.4)
- lg: 0 8px 32px rgba(0,0,0,0.5)
- glow: 0 0 20px rgba(99,230,208,0.08)（卡片悬浮发光）
- glow-lg: 0 0 40px rgba(99,230,208,0.12)

## 圆角
- sm: 6px, 默认: 10px, lg: 14px, xl: 20px

## 字体
使用 Inter、PingFang SC、Microsoft YaHei。等宽字体 JetBrains Mono / Fira Code。
数字要清晰稳重。

## 组件规范
- **玻璃卡片 (glass-card)**：半透明 surface + backdrop-blur(16px) + 边框 + 阴影。hover 时边框变亮、阴影加深、微发光。
- **输入框 (jh-input)**：rgba(255,255,255,0.04) 背景 + 边框，focus 时青色边框 + 青色光晕。
- **按钮主 (jh-btn-primary)**：青色背景 + 深色文字 + 青色阴影，hover 阴影加深 + 上移 1px。
- **按钮次 (jh-btn-secondary)**：半透明背景 + 边框，hover 背景加深。
- **标签 (jh-badge)**：圆角胶囊形，4 种颜色变体（accent/info/warning/danger）。
- **多空观点卡片**：青色/红色区分。
- **裁判裁决卡片**：金色强调。
- **数据指标卡**：grid 布局展示。
- **策略教练对话面板**：右侧固定宽度面板。

## 动效
- 卡片悬浮微微发光（glow 阴影增强）
- 页面入场 fadeInUp（opacity + translateY）
- 骨架屏 shimmer 动画
- 数字增长 countUp 动画
- 按钮 hover 上移 1px + 阴影增强

## 布局
- 深色背景 + 顶部径向渐变光晕
- 导航栏 sticky + backdrop-blur
- 卡片使用半透明 surface + 毛玻璃效果
- 强调色用于多空观点区分（青色多头、红色空头）
- 最大宽度约束（首页 4xl、搜索 2xl、卷宗 3xl）

## 禁忌
不要用赌博感视觉，不要承诺夸张收益，不要使用低可信素材。
不要使用纯白文字（用 #eef2ff），不要使用高饱和度颜色大面积铺底。
