# TODO.md — TradeTrail 待辦清單

---

## Phase 0：地基 ✅ 完成

- [x] **確認 index.html 可正常接入 RR**
  - postMessage 協定驗證：20 PASS（tests/test_rr_protocol.py）
  - 修復 race condition（dataReady.then）、空資料無限 reset

- [x] **建 `scripts/` 目錄，寫資料預處理腳本**
  - scripts/fetch_data.py：yfinance + pandas，幾秒完成
  - 輸出 data/{symbol}.json，含完整技術指標

- [x] **定義靜態 JSON 格式**
  - 22 欄位規格補進 PROJECT.md
  - MA / RSI / KD / MACD / Bollinger 全採業界標準參數

- [x] **美股標的資料備妥**
  - SPY / QQQ / AAPL / NVDA / TSLA，2015-2026，2533 train + 252 test

- [x] **標的切換**
  - Symbol 按鈕列，切換後重載資料 + 送 gameInfo + resetEnv

- [x] **部署上線**
  - https://tradetrail.leaflune.org/（Cloudflare Pages，master 分支）

---

## Phase 1：配置化 UI（進行中）

- [ ] **State 配置 UI**
  - 用戶勾選哪些技術指標進入 State Vector（RSI / MACD / KD / MA 等）
  - State Vector 維度動態計算，sendGameInfo 跟著更新 stateInfo
  - 設計考量：bin 的選法——固定 bin 還是讓用戶設定？先固定，後期再開放

- [ ] **訓練時段選擇器完善**
  - 現有：季度格子（Q1-Q4 × 年份），可多選
  - 缺少：快選按鈕（全選 / 近 3 年 / 近 1 年）
  - 缺少：目前篩選後資料量的顯示（選太少 step 可能不夠訓練）

---

## Phase 2：KPI & 視覺化（之後）

- [ ] **KPI 面板完整版**
  - 總報酬率、最大回撤（Max Drawdown）、Sharpe Ratio、勝率
  - 訓練期 vs 回測期分開顯示

- [ ] **K 線技術指標疊加**
  - 根據 State 配置，同步在 K 線圖畫出對應指標線

- [ ] **Equity Curve 細化**
  - 回測後顯示完整曲線，標出買賣點

---

## 擱置 / 未來想法

- [ ] 多資產同時持有 → 架構複雜度大增，先做單資產版本
- [ ] 即時資料（非歷史回測）→ 需要串接付費 API，非近期目標
- [ ] BTC / 加密貨幣 → 等美股版本穩定後再加

---

## 決策紀錄

- **不採用 CNN**：技術指標直接作為 State，不需要預先訓練預測模型。
- **動作空間固定離散**：買入 / 持有 / 賣出（3 選項）。資金粒度由 N 份控制。
- **MA 命名用根數**：ma5 / ma20，不標時間單位，符合業界慣例。
- **指標參數不自定義**：全採 TradingView 預設值（RSI-14、KD 14/3/3、MACD 12/26/9）。
