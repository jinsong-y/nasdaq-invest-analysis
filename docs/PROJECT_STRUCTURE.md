# 项目结构说明

## 顶层目录

| 目录 | 用途 |
| :--- | :--- |
| `data/` | 原始数据与清洗后的市场/基金数据 |
| `docs/` | 策略规划、数据清单、项目结构说明 |
| `reports/` | 回测产物、HTML 报告、项目总结 |
| `scripts/` | 可直接运行的数据抓取与回测脚本 |
| `src/` | 回测核心代码 |
| `tests/` | 单元测试 |

## 文档目录

| 路径 | 说明 |
| :--- | :--- |
| `docs/strategy/NASDQ_STRATEGY_V2.md` | 信号体系设计 |
| `docs/strategy/NASDQ_BACKTEST_PLAN.md` | 回测总体方案 |
| `docs/strategy/NASDQ_PARAMETER_OPTIMIZATION.md` | 参数网格与鲁棒性方案 |
| `docs/DATA_INVENTORY.md` | 数据字段、覆盖年份、缺口说明 |
| `docs/superpowers/` | 实施过程中的计划和规格记录 |

## 数据目录

| 路径 | 说明 |
| :--- | :--- |
| `data/raw/fred/` | FRED 原始 CSV |
| `data/raw/cnn/` | CNN Fear & Greed 原始数据 |
| `data/raw/funds/` | 基金净值原始抓取数据 |
| `data/processed/market_indicators.csv` | 合并后的市场指标日频表 |
| `data/processed/funds/` | 10 只基金的清洗净值数据 |
| `data/processed/data_manifest.json` | 市场数据 manifest |
| `data/processed/funds/funds_manifest.json` | 基金数据 manifest |

## 代码目录

| 路径 | 说明 |
| :--- | :--- |
| `src/version_a/config.py` | 参数、样本区间、资金规则 |
| `src/version_a/data.py` | 市场数据读取 |
| `src/version_a/features.py` | SMA、分位数、结构指标等特征 |
| `src/version_a/engine.py` | 机械定投与策略定投回测引擎 |
| `src/version_a/grid.py` | 参数网格、排序、甜品区间判断 |
| `src/version_a/metrics.py` | ROI、回撤、成本等指标汇总 |
| `src/version_a/report.py` | Version A/B HTML 报告生成 |
| `src/version_c/` | PE 百分位策略回测核心代码 |
| `src/market_regime/` | 市场状态 Dashboard、状态划分、HTML 报告生成 |

## 脚本目录

| 路径 | 说明 |
| :--- | :--- |
| `scripts/fetch_data.py` | 拉取并合并市场指标数据 |
| `scripts/fetch_fund_nav.py` | 拉取基金历史净值 |
| `scripts/run_version_a_backtest.py` | 运行 Version A 参数网络回测 |
| `scripts/run_version_b_funds.py` | 运行 Version B 基金净值测算 |
| `scripts/fetch_nasdaq100_pe.py` | 抓取纳指 PE 月度历史 |
| `scripts/run_version_c_pe_backtest.py` | 运行 Version C PE 百分位回测 |
| `scripts/run_market_regime_dashboard.py` | 生成市场状态双语 Dashboard |
| `scripts/evaluate_market_regime.py` | 评估市场状态历史表现和已知日期 |
| `scripts/run_market_regime_robustness.py` | 阈值网格、极端年份、walk-forward 鲁棒性测试 |

## 报告目录

| 路径 | 说明 |
| :--- | :--- |
| `reports/version_a/` | 正式 Version A 参数网络结果 |
| `reports/version_b_funds/` | Version B 真实基金净值测算 |
| `reports/version_c_pe/` | Version C PE 百分位回测结果 |
| `reports/version_c_pe_5000/` | Version C 触发日 5000 买入预算全样本结果 |
| `reports/version_c_pe_5000_2020_2026/` | Version C 触发日 5000 买入预算 2020-2026 结果 |
| `reports/market_regime/` | 市场状态双语 Dashboard、latest JSON、daily regimes |
| `reports/market_regime_evaluation/` | 市场状态历史评估、forward returns、已知日期复盘 |
| `reports/market_regime_robustness/` | 推荐阈值配置、grid results、walk-forward、误判复盘 |
| `reports/project_summary/` | 面向阅读的项目总结和总结图 |
| `reports/version_a_smoke/` | 小样本冒烟测试产物 |
| `reports/version_a_benchmark/` | 基准/历史中间产物 |

## 推荐阅读顺序

1. `reports/project_summary/PROJECT_SUMMARY.md`
2. `reports/version_a/index.html`
3. `reports/version_b_funds/index.html`
4. `reports/market_regime/index.html`
5. `reports/market_regime_robustness/index.html`
6. `docs/strategy/NASDQ_STRATEGY_V2.md`
7. `docs/PROJECT_STRUCTURE.md`
