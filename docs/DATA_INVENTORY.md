# 数据清单

- 统一样本起点：`2000-01-03`
- 生成时间 UTC：`2026-05-07T23:52:05+00:00`
- 原始 FRED 数据：`data/raw/fred/*.csv`
- 原始 CNN/FinHacker 数据：`data/raw/cnn/*.json`
- 合并日频指标表：`data/processed/market_indicators.csv`
- 机器可读 manifest：`data/processed/data_manifest.json`

## 已获取字段覆盖

| 字段 | 行数 | 起始日期 | 截止日期 |
| :--- | ---: | :--- | :--- |
| `ndx` | 6626 | 2000-01-03 | 2026-05-06 |
| `vxn` | 6352 | 2001-02-02 | 2026-05-06 |
| `vix` | 6655 | 2000-01-03 | 2026-05-06 |
| `ndxe` | 5246 | 2005-06-28 | 2026-05-06 |
| `sox` | 5326 | 2004-09-02 | 2026-05-06 |
| `cnn_fear_greed` | 3859 | 2011-01-03 | 2026-05-07 |
| `spx` | 3858 | 2011-01-03 | 2026-05-06 |
| `ndxe_ndx` | 5246 | 2005-06-28 | 2026-05-06 |
| `sox_ndx` | 5326 | 2004-09-02 | 2026-05-06 |

## 数据源

- FRED graph CSV：https://fred.stlouisfed.org/graph/fredgraph.csv
- FinHacker 页面：https://www.finhacker.cz/en/fear-and-greed-index-historical-data-and-chart/
- FinHacker 历史数据接口：https://www.finhacker.cz/wp-content/custom-api/fear-greed-data.php
- FinHacker 实时 JSON：https://www.finhacker.cz/wp-content/data/fng-live.json

## 尚缺数据

- CNN Fear & Greed 源数据从 2011-01-03 开始；2000-01-03 到 2010 年末的合并表中该字段为空。
- `fund_nav`：文档的真实执行回测 Version B 需要具体 QDII 基金历史净值，但当前仓库没有基金代码或名称；按 fall-fast 原则未替换成任意基金或 ETF。
