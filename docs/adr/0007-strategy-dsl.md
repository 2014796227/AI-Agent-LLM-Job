# ADR-0007：策略 DSL——白名单、语义契约、拒绝执行 LLM 生成代码

- 状态：已接受
- 日期：2026-08-15
- 决策人：＿＿＿＿（待签名）
- 关联：蓝图 dsl.py / test_dsl.py；第二、四轮评审（操作数表达力与校验缺口）

## 决策 1：LLM 只翻译，不写代码

LLM 职责=把自然语言策略翻译为受 pydantic schema 严格约束的 JSON（StrategySpec）；确定性编译器把 DSL 编译为 pandas 信号。**全程无 eval/exec** → 无注入面、可复现、可单测。备选（拒绝）：让 LLM 生成 pandas 代码在沙箱执行——注入/稳定性/可复现三重风险，P2 再议。

## 决策 2：操作数与条件模型（表达力与约束的平衡）

- 操作数：`ind{ma/ema/rsi/hhv/llv/ret/vol_ma, n∈[2,500]}` | `price{close/open/high/low/volume}` | `const`（discriminated union，extra=forbid）
- 条件：gt/lt/cross_up/cross_down（**左操作数必须是序列**；右可为序列或常数——RSI(14)<30、close 上穿 hhv(20) 由此可表达）；and/or 嵌套深度≤3（递归校验实现）
- **放弃 v7 的 fast<slow 硬约束**（第四轮评审）：`cross_up(ma20, ma5)` 是"慢线上穿快线"的合法策略而非语法错误，该约束本非语义不变式；改为提示词约定（金叉=快线在左）+ 评测 spec_match 断言。保留的硬校验=同族同窗口 cross 拒绝（恒等序列永不交叉）
- 语义契约逐指标固化（含 hhv/llv=前 n 日极值不含当日、RSI 横盘=50、entry/exit 同日=exit 优先），十类拒绝场景+语义手算全部有单测

## 决策 3：越界请求=正确拒绝（产品能力而非缺陷）

白名单外（LSTM/多标的/网格/套利）→ Supervisor 输出 refuse → task_refused 事件 + 明确"支持范围"提示；评测含 refusal_ok 用例（正确拒绝=通过）。v1 单标的在 schema 层强制（universe max_length=1）。

## 后果与妥协

- 表达力边界=白名单策略族；扩展路径=新指标入白名单+语义单测，或 P2 沙箱解释器
- "看似合法但编译出垃圾"的输入（n 超数据长度等）在编译期显式报错（CompileError 回传模型自纠错），绝不产出全 NaN 信号
