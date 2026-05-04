# 数据清单

- 统一样本起点：`2000-01-03`
- 生成时间 UTC：`2026-05-04T23:53:03+00:00`
- 原始 FRED 数据：`data/raw/fred/*.csv`
- 原始 CNN/FinHacker 数据：`data/raw/cnn/*.json`
- 合并日频指标表：`data/processed/market_indicators.csv`
- 机器可读 manifest：`data/processed/data_manifest.json`

## 已获取字段覆盖

| 字段 | 行数 | 起始日期 | 截止日期 |
| :--- | ---: | :--- | :--- |
| `ndx` | 6623 | 2000-01-03 | 2026-05-01 |
| `vxn` | 6349 | 2001-02-02 | 2026-05-01 |
| `vix` | 6652 | 2000-01-03 | 2026-05-01 |
| `ndxe` | 5243 | 2005-06-28 | 2026-05-01 |
| `sox` | 5323 | 2004-09-02 | 2026-05-01 |
| `cnn_fear_greed` | 3856 | 2011-01-03 | 2026-05-04 |
| `spx` | 3855 | 2011-01-03 | 2026-05-01 |
| `ndxe_ndx` | 5243 | 2005-06-28 | 2026-05-01 |
| `sox_ndx` | 5323 | 2004-09-02 | 2026-05-01 |

## 数据源

- FRED graph CSV：https://fred.stlouisfed.org/graph/fredgraph.csv
- FinHacker 页面：https://www.finhacker.cz/en/fear-and-greed-index-historical-data-and-chart/
- FinHacker 历史数据接口：https://www.finhacker.cz/wp-content/custom-api/fear-greed-data.php
- FinHacker 实时 JSON：https://www.finhacker.cz/wp-content/data/fng-live.json

## 尚缺数据

- CNN Fear & Greed 源数据从 2011-01-03 开始；2000-01-03 到 2010 年末的合并表中该字段为空。
- `fund_nav`：文档的真实执行回测 Version B 需要具体 QDII 基金历史净值，但当前仓库没有基金代码或名称；按 fall-fast 原则未替换成任意基金或 ETF。
