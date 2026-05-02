# CHANGELOG — TradeTrail

> 記錄功能完整上線的里程碑、架構層級決策、破壞性變更。
> 小 bug fix 和文字調整見 git log。

---

## v0.1 — Phase 0 完成（2026-05-01）

- **部署上線**：https://tradetrail.leaflune.org/（Cloudflare Pages，master 分支）
- **資料層**：scripts/fetch_data.py，SPY/QQQ/AAPL/NVDA/TSLA 日K，2015-2026
- **postMessage 協定**：移除 CNN，State 改為技術指標；修復 race condition（dataReady.then）
- **協定驗證**：tests/test_rr_protocol.py，Playwright 24 PASS

## v0.2 — Phase 1 State 配置 UI（2026-05-01）

- **STATE_CATALOG**：RSI / KD%K / KD%D / MACD / MA偏離% / Bollinger 六個可選指標
- **動態 stateInfo**：勾選即更新 gameInfo，RR Q-table 自動重置
- **UX**：季度格子改年份選擇；details 折疊面板；X 軸月份 / 年份邊界刻度
