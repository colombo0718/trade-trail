# PROJECT.md — TradeTrail 專案快速指引

## 這個專案是什麼

**TradeTrail (TT)** 是一個可配置的金融市場 RL 訓練環境，作為 RR（ReinforceLab）平台的旗艦應用之一。
面向對量化交易有興趣的使用者，讓用戶自行組裝交易環境，交給 RR 的 RL Agent 學習策略，再透過回測曲線驗證結果。

隸屬：LeafLune Edutainment Studio
縮寫：TT
部署目標：LeafLune 子域（如 `tradetrail.leaflune.org`）

---

## 核心流程

```
用戶選標的 + 組裝 State + 劃定時段
        ↓
TT 建構環境，透過 RR postMessage 協定接入 Agent
        ↓
RL Agent 訓練（RR 控制）
        ↓
回測曲線 + KPI 驗證策略表現
```

---

## 資料層

- **主要市場：** 美股（可擴充至其他市場）
- **資料來源：** yfinance / pandas-ta 預處理後靜態打包，或輕量 Python API
- **資料格式：** 歷史 OHLCV + 預計算技術指標
- **技術指標：** MA、RSI、MACD、布林通道等常用指標
- **預測訊號（選配）：** 每個標的以 1D CNN 預跑出預測訊號，可納入 State（視算力決定）

---

## 環境配置（用戶可調）

| 配置項 | 說明 |
|--------|------|
| 標的選擇 | 美股標的，可多選 |
| State 組裝 | 勾選哪些指標 / 預測值進入 State Vector |
| 訓練時段 | In-sample 時段（RL 訓練用） |
| 回測時段 | Out-of-sample 時段（策略驗證用） |
| 動作空間 | 買 / 賣 / 持有（離散）或連續倉位比例 |
| Reward 配置 | 每步 PnL、Sharpe ratio 增量等可選 |

---

## RR 介面（postMessage 協定）

與 RR 主平台的通訊遵循標準協定（`RR平台可控遊戲環境宣告與通訊協定.md`）：

```
gameInfo：宣告 stateInfo（State Vector 維度）、actionInfo（買/賣/持有）
reward_state：{ state, reward, done, sessionId, ticks }
```

動作空間為離散（買 0 / 持有 1 / 賣 2）或連續（待 DDPG/SAC 實裝後啟用）。

---

## 視覺化（即時顯示於訓練過程）

- K 線圖（含技術指標疊加）
- 持倉狀態（多 / 空 / 空手）
- 資產曲線（Equity Curve）
- KPI：總報酬、最大回撤（Max Drawdown）、Sharpe Ratio

---

## 技術棧

| 功能 | 技術 |
|------|------|
| 前端 | 純 HTML / JS 單頁應用 |
| K 線圖 | lightweight-charts（TradingView 開源版）或 Plotly |
| 資料預處理 | Python（yfinance + pandas-ta），靜態打包或輕量 API |
| 部署 | LeafLune 子域，Cloudflare Pages（前端）|

---

## 當前起點

`index.html` 來自 RR 的 `games/btc_trading.html`——BTC 歷史資料的 RL 交易環境原型，元智大學課程專題成果，CNN+RL 架構。這是 TT 的開發基礎，後續在此擴充配置化能力與多標的支援。

---

## 開發規範

- 遊戲邏輯與 RR 通訊介面分離，TT 只負責環境，不負責 RL 算法
- 資料預處理腳本放 `scripts/` 目錄，前端只讀靜態 JSON
- commit 訊息中英文皆可，說明改了什麼
- 部署前確認 RR postMessage 協定版本相容
