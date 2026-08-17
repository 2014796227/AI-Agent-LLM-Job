# 评测报告（脚本生成，人工结论只允许追加于末尾）

- commit: `no-git`
- 时间: 2026-08-16T17:25:09.376591

| 用例 | 状态 | tools | spec | backtest | numbers | refusal | cite | judge |
|---|---|---|---|---|---|---|---|---|
| backtest_001 | failed | True | True | True | None | None | None | None |
| bt_ma_fast | failed | False | False | None | None | None | None | None |
| bt_ma_mid | done | None | True | True | True | None | None | False |
| bt_ema | running | None | True | True | None | None | None | None |
| breakout_001 | failed | None | False | None | None | None | None | None |
| bt_rsi_obos | failed | None | False | None | None | None | None | None |
| bt_momentum | done | None | True | True | True | None | None | True |
| bt_vol_combined | done | True | None | True | True | None | None | False |
| bt_2024_window | done | None | True | True | True | None | None | True |
| bt_highvol_breakout | done | None | True | True | True | None | None | False |
| strategy_reject_001 | done | None | None | None | None | True | None | False |
| bt_reject_grid | done | None | None | None | None | True | None | False |
| bt_reject_multi | done | None | None | None | None | False | None | True |
| rag_drawdown_ctl | done | True | None | None | None | None | True | True |
| rag_kelly | done | None | None | None | None | None | True | True |
| rag_lookahead | done | None | None | None | None | None | True | False |
| rag_survivorship | done | None | None | None | None | None | True | True |
| rag_overfit | done | None | None | None | None | None | True | True |
| rag_sharpe | done | None | None | None | None | None | True | True |
| rag_voltarget | done | None | None | None | None | None | True | True |
| rag_atr | done | None | None | None | None | None | True | True |
| rag_ttest | done | None | None | None | None | None | True | False |
| rag_walkforward | done | None | None | None | None | None | True | True |
| rag_adjust | done | None | None | None | None | None | True | True |
| rag_t1 | done | None | None | None | None | None | False | False |
| rag_mt_revenue | done | None | None | None | None | None | True | False |
| rag_mt_netprofit | done | None | None | None | None | None | True | False |
| rag_mt_cashflow | done | None | None | None | None | None | False | True |
| rag_mt_product | done | None | None | None | None | None | True | False |
| rag_mt_2024_rev | done | None | None | None | None | None | True | True |
| rag_wly_revenue | done | None | None | None | None | None | True | False |
| rag_wly_profit | done | None | None | None | None | None | True | True |
| rag_kb_boundary | done | None | None | None | None | None | True | False |
| refuse_arb | done | None | None | None | None | True | None | False |
| refuse_hft | done | None | None | None | None | True | None | False |
| refuse_leverage | done | None | None | None | None | False | None | True |
| refuse_ml_portfolio | done | None | None | None | None | True | None | False |
| refuse_crypto | done | None | None | None | None | False | None | False |
| rpt_trend_2023 | running | True | None | None | None | None | None | None |
| rpt_trend_2024 | done | True | None | None | None | None | None | False |
| rpt_vol | running | True | None | None | None | None | None | None |
| rpt_monthly | done | True | None | None | None | None | None | True |
| rpt_risk | done | True | None | None | None | None | None | False |
| rpt_range_high_low | done | True | None | None | None | None | None | True |
| rpt_kb_mix | done | True | None | None | None | None | True | False |
| rpt_two_question | degraded | True | None | True | None | None | None | None |
| rpt_trend_2023 | done | True | None | None | None | None | None | False |
| rag_drawdown_ctl | done | True | None | None | None | None | True | True |
| refuse_arb | done | None | None | None | None | True | None | True |
time="2026-08-17T10:07:44+08:00" level=warning msg="The \"DB_PASS\" variable is not set. Defaulting to a blank string."
