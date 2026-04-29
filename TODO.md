# TODO.md — TradeTrail 待辦清單

---

## Phase 0：地基（現在可以開始）

- [ ] **確認 index.html 可正常接入 RR**
  - 把 `btc_trading.html` 搬進來的版本在 RR iframe 裡跑通，確認 postMessage 協定正常收發
  - 這是所有後續功能的前提，先讓「一個資產、現有 BTC 資料」的版本穩定

- [ ] **建 `scripts/` 目錄，寫第一支資料預處理腳本**
  - 輸入：yfinance 抓下來的歷史 OHLCV
  - 輸出：靜態 JSON，格式見下方定義
  - 先以 BTC 為對象，確認格式後再推廣到美股
  - 不需要 CNN，直接算技術指標輸出即可（幾秒完成）

- [ ] **定義靜態 JSON 格式**（決定後補進 PROJECT.md）
  - 必要欄位：`date`、`open`、`high`、`low`、`close`、`volume`
  - 技術指標欄位：`ma5`、`ma20`、`rsi`、`macd`、`macd_signal`、`boll_upper`、`boll_lower`
  - 市場標記：`market`（`bull` / `bear`，以 MA20 為基準）
  - 分段標記：`phase`（`train` / `test`）

---

## Phase 1：多標的 & 配置化

- [ ] **加入美股標的資料**
  - 選定初始股票清單（建議從 SPY、AAPL、TSLA、NVDA、QQQ 開始）
  - 用 `scripts/` 腳本批量下載並打包成靜態 JSON

- [ ] **State 配置 UI**
  - 用戶可勾選哪些技術指標進入 State Vector（MA、RSI、MACD、布林等）
  - State Vector 維度動態計算，回傳給 RR 的 `stateInfo`（含 `bin`）跟著更新

- [ ] **訓練 / 回測時段選擇器**
  - in-sample（訓練）時段選擇
  - out-of-sample（回測）時段選擇
  - UI：日期範圍 picker 或預設時段快選（近 1 年 / 近 3 年 / 全部）

- [ ] **標的切換**
  - 下拉選單切換標的，環境重置，資料重新載入

---

## Phase 2：KPI & 視覺化完善

- [ ] **Equity Curve 完整顯示**
  - 訓練過程即時更新，回測後顯示完整曲線

- [ ] **KPI 面板**
  - 總報酬率、最大回撤（Max Drawdown）、Sharpe Ratio、勝率
  - 訓練期 vs 回測期分開顯示

- [ ] **K 線技術指標疊加顯示**
  - 根據用戶勾選的 State 指標，同步在 K 線圖上畫出對應指標線

---

## 擱置 / 未來想法

- [ ] 多資產同時持有 → 架構複雜度大增，先做單資產版本
- [ ] 即時資料（非歷史回測）→ 需要串接付費 API，非近期目標

---

## 決策紀錄

- **不採用 CNN**：技術指標直接作為 State，不需要預先訓練預測模型。原 btc_trading.html 的 CNN 架構是課程專題遺留，TT 不繼承這個設計。
- **動作空間固定離散**：買入 / 持有 / 賣出（3 選項），連續動作空間不在規劃內。資金粒度由「拆幾份 N」這個環境參數控制。
