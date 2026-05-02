# Nasdaq DCA Backtest

纳指定投信号体系回测项目。项目目标是验证一套由 SMA 趋势、VIX/VXN 波动率、CNN Fear & Greed 情绪、NDXE/SOX 内部结构组成的定投节奏系统，是否能稳定跑赢机械定投。

![纳指定投体系回测总结](reports/project_summary/assets/nasdaq_backtest_summary_image2.png)

## 快速入口

| 内容 | 路径 |
| :--- | :--- |
| 项目总结 | `reports/project_summary/PROJECT_SUMMARY.md` |
| Version A 总览 HTML | `reports/version_a/index.html` |
| Version B 基金 HTML | `reports/version_b_funds/index.html` |
| Version C PE 回测 HTML | `reports/version_c_pe/index.html` |
| 数据清单 | `docs/DATA_INVENTORY.md` |
| 项目结构说明 | `docs/PROJECT_STRUCTURE.md` |

## 当前结论

- Version A 跑了 33,648 组参数，0 组跑赢机械定投。
- Version B 测了 10 只纳指相关基金，4 只小幅正超额，最佳超额约 +0.37%。
- 当前信号体系更适合作为风控和节奏参考，不宜直接替代机械定投。
- Version C 已加入 PE 百分位回测入口；按 `2000-01-03` 到 `2026-05-01` 口径，PE 策略终值约 `1014.23` 万，机械定投约 `1337.54` 万，少约 `323.31` 万。
- 当前这套 PE 百分位规则同样没有跑赢机械定投，现阶段更适合作为估值风控参考，而不是直接替代持续定投。

## 常用命令

使用项目内 `.venv`：

```bash
.venv/bin/python -m unittest tests/test_fetch_data.py tests/test_version_a.py tests/test_version_c.py
.venv/bin/python scripts/run_version_a_backtest.py
.venv/bin/python scripts/run_version_b_funds.py
.venv/bin/python scripts/fetch_nasdaq100_pe.py
.venv/bin/python scripts/run_version_c_pe_backtest.py
```

如只想查看现有结果，直接打开 `reports/` 下的 HTML 或 Markdown 文件即可。
