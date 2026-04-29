# PROJECT.md — TradeTrail 專案快速指引

## 這個專案是什麼

**TradeTrail (TT)** 是一個個性化的交易策略訓練平台，作為 RR（ReinforceLab）平台的大人向旗艦應用。

TT 的核心不是提供指標與線圖，而是讓用戶**設計自己的訓練框架**：
選擇哪些技術指標作為 Agent 的觀察依據、資金如何分批調度、要在哪段市況（牛市 / 熊市 / 特定時段）中建立策略直覺——然後把這套框架交給 RL Agent 學習，再用 out-of-sample 回測驗證結果。

這三個配置選擇本身就是更高層次的 RL 議題：用戶在做的是**觀察空間工程（observation space design）**——選哪些 State 進來，在很大程度上決定了 Agent 能學到什麼。TT 把這個決策權交給用戶，讓用戶用直覺假設去實驗「什麼樣的市場資訊能訓練出更好的策略」。

隸屬：LeafLune Edutainment Studio
縮寫：TT
正式網址：https://tradetrail.leaflune.org/
GitHub：https://github.com/colombo0718/trade-trail
RR 正式版：https://reinroom.leaflune.org/

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
- **資料來源：** yfinance，Python 預處理後靜態打包為 JSON
- **存放位置：** `data/<symbol>.json`（如 `data/btc_usd.json`）
- **預測訊號：** 不採用 CNN，技術指標本身即為 State 的完整來源

### 靜態 JSON 格式

**檔案頂層結構：**

```json
{
  "symbol":      "BTC-USD",
  "interval":    "1h",
  "total_steps": 17413,
  "train_steps": 16693,
  "test_steps":  720,
  "data":        [ ... ]
}
```

**data 陣列每筆記錄：**

| 欄位 | 類型 | 說明 |
|------|------|------|
| `step` | int | 全局步號（train 從 0 開始，test 接續） |
| `date` | string | ISO 8601，如 `2024-04-27T19:00:00` |
| `open` | float | 開盤價 |
| `high` | float | 最高價 |
| `low` | float | 最低價 |
| `close` | float | 收盤價 |
| `volume` | float | 成交量 |
| `ma5` | float | 5 期移動平均 |
| `ma10` | float | 10 期移動平均 |
| `ma20` | float | 20 期移動平均 |
| `ma60` | float | 60 期移動平均 |
| `vol_ma5` | float | 成交量 5 期移動平均 |
| `rsi` | float | RSI-14，範圍 0–100 |
| `stoch_k` | float | KD 指標 %K（14/3/3），範圍 0–100 |
| `stoch_d` | float | KD 指標 %D，範圍 0–100 |
| `macd` | float | MACD 線（EMA12 − EMA26） |
| `macd_signal` | float | MACD Signal 線（MACD 的 EMA9） |
| `boll_upper` | float | 布林上軌（MA20 + 2σ） |
| `boll_lower` | float | 布林下軌（MA20 − 2σ） |
| `market` | string | `"bull"` 或 `"bear"`（close ≥ MA20 為 bull） |
| `phase` | string | `"train"` 或 `"test"` |

**注意：**
- MA 欄位數字代表 K 棒根數，不是天數（1h 資料的 ma20 = 20小時均線）
- 所有指標均為原始值，State 正規化在前端訓練時動態處理
- 腳本：`scripts/fetch_data.py`，參數在檔案頂部設定區調整

---

## 環境配置（用戶可調）

| 配置項 | 說明 |
|--------|------|
| 標的選擇 | 美股標的，可多選 |
| State 組裝 | 勾選哪些指標 / 預測值進入 State Vector |
| 訓練時段 | In-sample 時段（RL 訓練用） |
| 回測時段 | Out-of-sample 時段（策略驗證用） |
| 動作空間 | 買 / 持有 / 賣（固定離散 3 選項） |
| 資金級距 | 將資金拆成 N 份，每次買賣 1 份（用戶可設定 N） |
| Reward 配置 | 每步 PnL、Sharpe ratio 增量等可選 |

---

## RR 介面（postMessage 協定）

與 RR 主平台的通訊遵循標準協定，完整規格見：
`C:\Users\USER\ReinforceLab\RR平台可控遊戲環境宣告與通訊協定.md`

```
gameInfo：宣告 stateInfo（State Vector 維度）、actionInfo（買/賣/持有）
reward_state：{ state, reward, done, sessionId, ticks }
```

動作空間為固定離散：買入 0 / 持有 1 / 賣出 2。
資金拆分粒度（N 份）為環境參數，由用戶在 UI 設定。

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

`index.html` 來自 RR 的 `games/btc_trading.html`——BTC 歷史資料的 RL 交易環境原型，元智大學課程專題成果。原版採用 CNN+RL 架構，TT 改以技術指標取代 CNN 預測訊號，動作空間維持離散三選項。這是 TT 的開發基礎，後續在此擴充配置化能力與多標的支援。

---

## 開發規範

- 遊戲邏輯與 RR 通訊介面分離，TT 只負責環境，不負責 RL 算法
- 資料預處理腳本放 `scripts/` 目錄，前端只讀靜態 JSON
- commit 訊息中英文皆可，說明改了什麼
- 部署前確認 RR postMessage 協定版本相容
