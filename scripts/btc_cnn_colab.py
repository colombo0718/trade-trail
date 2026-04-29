# ============================================================
#  BTC/USDT 1D CNN 量化交易回測系統 — Google Colab 版
#  使用方式：上傳到 Colab 後執行，或直接貼入儲存格
# ============================================================

# ── 安裝缺少的套件（Colab 已內建 tensorflow / pandas / sklearn）──
import subprocess
subprocess.run(['pip', 'install', 'mplfinance', 'yfinance', '-q'], check=True)

# ── 匯入 ─────────────────────────────────────────────────────
import warnings
warnings.filterwarnings('ignore')

import json
import yfinance as yf
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import mplfinance as mpf
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error
import tensorflow as tf
from tensorflow import keras

tf.get_logger().setLevel('ERROR')
print(f'TensorFlow 版本：{tf.__version__}')

# ─────────────────────────────────────────────────────────────
# 設定區（可自由修改來測試不同參數）
# ─────────────────────────────────────────────────────────────
SYMBOL          = 'BTC-USD'

# ── 資料週期設定 ──────────────────────────────────────────
# '1h'：最近 730 天（yfinance 限制），適合短期測試
# '1d'：從 2014 年至今（約 4000 筆），訓練集大幅增加，推薦使用
INTERVAL        = '1h'

# 測試集筆數（依週期調整）
# 1h → 24 * 30 = 720（最後 30 天）
# 1d → 30（最後 30 天）
TEST_BARS       = 720            # 測試集固定取最後 N 根

WINDOW_SIZE     = 24             # 滑動窗口大小（同單位的 K 棒數）
EPOCHS          = 50
BATCH_SIZE      = 32
INITIAL_CAPITAL = 10_000         # 初始資金 (USDT)
CANDLES_TO_SHOW = 200            # K線圖顯示根數

# Phase 1：CNN → State 閾值設定（預測漲幅 %）
THRESHOLDS = [1.0, 0.3, -0.3, -1.0]
#   > +1.0%  → State 0（大漲）
#   +0.3~1.0 → State 1（小漲）
#   -0.3~0.3 → State 2（持平）
#   -1.0~-0.3→ State 3（小跌）
#   < -1.0%  → State 4（大跌）


# ═════════════════════════════════════════════════════════════
# 1. 資料抓取
# ═════════════════════════════════════════════════════════════

def fetch_klines(interval=INTERVAL):
    """
    用 yfinance 抓 BTC-USD OHLCV 資料（Yahoo Finance）
    - 1h：period='730d'（yfinance 限制，無法更早）
    - 1d：period='max'（從 2014 年至今，約 4000 筆）
    """
    yf_symbol = 'BTC-USD'
    period = '730d' if interval == '1h' else 'max'
    df = yf.download(yf_symbol, period=period, interval=interval,
                     auto_adjust=True, progress=False)

    # 新版 yfinance 回傳 MultiIndex 欄位，先攤平再轉小寫
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [c.lower() for c in df.columns]
    df.index.name = 'open_time'

    # 只保留需要的欄位
    df = df[['open', 'high', 'low', 'close', 'volume']].copy()
    df.sort_index(inplace=True)

    # 讓 index 變成 tz-naive（避免後續日期比較出錯）
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    return df


# ═════════════════════════════════════════════════════════════
# 2. 特徵工程
# ═════════════════════════════════════════════════════════════

def add_features(df):
    df = df.copy()

    df['ma5']  = df['close'].rolling(5).mean()
    df['ma20'] = df['close'].rolling(20).mean()

    df['return']     = df['close'].pct_change()
    df['volatility'] = df['return'].rolling(10).std()

    # RSI-14
    delta = df['close'].diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    df['rsi'] = 100 - 100 / (1 + gain / (loss + 1e-9))

    # MACD
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd']        = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()

    df.dropna(inplace=True)
    return df

FEATURE_COLS = ['open', 'high', 'low', 'close', 'volume',
                'ma5', 'ma20', 'return', 'volatility', 'rsi', 'macd', 'macd_signal']


# ═════════════════════════════════════════════════════════════
# 3. 資料前處理
# ═════════════════════════════════════════════════════════════

def make_sequences(scaled, window=WINDOW_SIZE):
    close_idx = FEATURE_COLS.index('close')
    X, y = [], []
    for i in range(len(scaled) - window):
        X.append(scaled[i : i + window])
        y.append(scaled[i + window, close_idx])
    return np.array(X), np.array(y)

def inverse_close(scaler, vals):
    close_idx = FEATURE_COLS.index('close')
    dummy = np.zeros((len(vals), len(FEATURE_COLS)))
    dummy[:, close_idx] = vals
    return scaler.inverse_transform(dummy)[:, close_idx]


# ═════════════════════════════════════════════════════════════
# 4. 1D CNN 模型
# ═════════════════════════════════════════════════════════════

def build_model(input_shape):
    inp = keras.Input(shape=input_shape)

    x = keras.layers.Conv1D(64, 3, padding='same', activation='relu')(inp)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.Conv1D(64, 3, padding='same', activation='relu')(x)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.MaxPooling1D(2)(x)

    x = keras.layers.Conv1D(128, 3, padding='same', activation='relu')(x)
    x = keras.layers.BatchNormalization()(x)
    x = keras.layers.GlobalAveragePooling1D()(x)

    x = keras.layers.Dense(64, activation='relu')(x)
    x = keras.layers.Dropout(0.2)(x)
    out = keras.layers.Dense(1)(x)

    model = keras.Model(inp, out)
    model.compile(optimizer='adam', loss='mse', metrics=['mae'])
    return model


# ═════════════════════════════════════════════════════════════
# 5. 回測
# ═════════════════════════════════════════════════════════════

def backtest(y_true, y_pred, initial_capital=INITIAL_CAPITAL):
    """
    策略：預測漲 → 買入（全倉做多）；預測跌 → 賣出平倉
    不做空、不加槓桿
    """
    capital, position = float(initial_capital), 0.0
    equity, trades = [], []

    for i in range(len(y_pred) - 1):
        cur  = float(y_true[i])
        pred = float(y_pred[i + 1])

        if pred > cur and position == 0 and capital > 0:
            position = capital / cur
            capital  = 0.0
            trades.append(('BUY', cur))
        elif pred <= cur and position > 0:
            capital  = position * cur
            position = 0.0
            trades.append(('SELL', cur))

        equity.append(capital + position * float(y_true[i]))

    if position > 0:
        capital = position * float(y_true[-1])
    equity.append(capital)
    equity = np.array(equity)

    total_return = (capital - initial_capital) / initial_capital * 100

    peak     = np.maximum.accumulate(equity)
    drawdown = (equity - peak) / (peak + 1e-9) * 100
    max_dd   = float(drawdown.min())

    wins, pairs, buy_px = 0, 0, None
    for side, px in trades:
        if side == 'BUY':
            buy_px = px
        elif side == 'SELL' and buy_px:
            pairs += 1
            wins  += int(px > buy_px)
            buy_px = None
    win_rate = wins / pairs * 100 if pairs > 0 else 0.0

    rets   = pd.Series(equity).pct_change().dropna()
    sharpe = float(rets.mean() / rets.std() * np.sqrt(24 * 365)) if rets.std() > 0 else 0.0

    return equity, {
        'initial_capital': initial_capital,
        'final_capital':   capital,
        'total_return':    total_return,
        'max_drawdown':    max_dd,
        'win_rate':        win_rate,
        'sharpe_ratio':    sharpe,
        'total_trades':    pairs,
        'trades':          trades,
    }


# ═════════════════════════════════════════════════════════════
# 6. 視覺化
# ═════════════════════════════════════════════════════════════

def plot_candlestick(df, n=CANDLES_TO_SHOW, save_path=None):
    df_plot = df.tail(n)[['open', 'high', 'low', 'close', 'volume']].copy()
    mc    = mpf.make_marketcolors(up='red', down='green',
                                  wick={'up': 'red', 'down': 'green'}, volume='in')
    style = mpf.make_mpf_style(marketcolors=mc, gridstyle='--')
    fig, axes = mpf.plot(df_plot, type='candle', volume=True,
                         title=f'{SYMBOL} {INTERVAL} Candlestick Chart (Last {n} Bars)',
                         style=style, figsize=(14, 7), returnfig=True)
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f'    儲存：{save_path}')
    plt.show()


def plot_prediction(dates, y_true, y_pred, save_path=None):
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(dates, y_true, label='Actual Price', color='steelblue', lw=1.5)
    ax.plot(dates, y_pred, label='Predicted Price', color='tomato',
            lw=1.2, ls='--', alpha=0.85)
    ax.set_title(f'BTC Close Price: Predicted vs Actual (Test Set) | Window={WINDOW_SIZE}h')
    ax.set_xlabel('Time')
    ax.set_ylabel('Price (USDT)')
    ax.legend()
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d'))
    ax.grid(alpha=0.3)
    fig.autofmt_xdate()
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f'    儲存：{save_path}')
    plt.show()


def plot_equity_curve(equity, metrics, save_path=None):
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(equity, color='mediumseagreen', lw=1.5, label='Strategy Equity')
    ax.axhline(metrics['initial_capital'], color='gray', ls='--', lw=1, label='Initial Capital')
    ax.set_title(
        f"Equity Curve (Window={WINDOW_SIZE}h)  |  Return {metrics['total_return']:+.2f}%  "
        f"Max Drawdown {metrics['max_drawdown']:.2f}%  "
        f"Sharpe {metrics['sharpe_ratio']:.3f}"
    )
    ax.set_xlabel('Time Step (Hours)')
    ax.set_ylabel('Equity (USDT)')
    ax.legend()
    ax.grid(alpha=0.3)
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f'    儲存：{save_path}')
    plt.show()


def plot_training_history(history, save_path=None):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot(history.history['loss'],     label='Train')
    axes[0].plot(history.history['val_loss'], label='Val')
    axes[0].set_title('Loss (MSE)')
    axes[0].set_xlabel('Epoch')
    axes[0].legend()
    axes[0].grid(alpha=0.3)

    axes[1].plot(history.history['mae'],     label='Train')
    axes[1].plot(history.history['val_mae'], label='Val')
    axes[1].set_title('MAE')
    axes[1].set_xlabel('Epoch')
    axes[1].legend()
    axes[1].grid(alpha=0.3)

    plt.suptitle(f'Training History (Window={WINDOW_SIZE}h)')
    plt.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f'    儲存：{save_path}')
    plt.show()


# ═════════════════════════════════════════════════════════════
# 7. 牛熊市標記
# ═════════════════════════════════════════════════════════════

def label_market(df, window=720):
    """
    以 MA{window}（30天均線）標記每個時間點的市場狀態。
    收盤價 >= MA → 'bull'，收盤價 < MA → 'bear'
    window=720 對應 1h 資料的 30 天。
    """
    ma = df['close'].rolling(window, min_periods=1).mean()
    labels = pd.Series('bear', index=df.index)
    labels[df['close'] >= ma] = 'bull'
    return labels


# ═════════════════════════════════════════════════════════════
# 8. [Phase 1] CNN 輸出 → 匯出 btc_states.json
# ═════════════════════════════════════════════════════════════

def export_btc_states(train_dates, y_true_train, y_pred_train, train_market, train_ohlcv,
                       test_dates,  y_true_test,  y_pred_test,  test_market, test_ohlcv,
                       path='btc_states.json'):
    """
    將訓練集＋測試集的真實價格與 CNN 預測漲幅一併匯出為 JSON。
    phase='train' 供 RL 訓練，phase='test' 供 RL 驗證績效。
    state 分類由 btc_trading.html UI 控制閾值後即時計算。

    JSON 格式：
    {
      "interval": "1h",
      "window_size": 24,
      "total_steps": N,
      "train_steps": M,   ← 前 M 步是訓練段
      "test_steps":  K,   ← 後 K 步是測試段
      "data": [
        { "step": 0,  "date": "...", "price": ..., "pred_return_pct": ..., "phase": "train" },
        ...
        { "step": M,  "date": "...", "price": ..., "pred_return_pct": ..., "phase": "test"  },
        ...
      ]
    }
    """
    data = []
    step = 0

    # ── 訓練段（CNN in-sample 預測，供 RL 學習策略）──
    for i in range(len(y_true_train) - 1):
        date_str = pd.Timestamp(train_dates[i]).strftime('%Y-%m-%dT%H:%M:%S') \
                   if i < len(train_dates) else ''
        pred_return = (float(y_pred_train[i + 1]) - float(y_true_train[i])) \
                      / (float(y_true_train[i]) + 1e-9) * 100
        o, h, l = (round(float(train_ohlcv[i, j]), 2) for j in range(3)) \
                  if i < len(train_ohlcv) else (0.0, 0.0, 0.0)
        data.append({
            'step':            step,
            'date':            date_str,
            'open':            o,
            'high':            h,
            'low':             l,
            'price':           round(float(y_true_train[i]), 2),
            'pred_return_pct': round(pred_return, 4),
            'phase':           'train',
            'market':          str(train_market[i]) if i < len(train_market) else 'bull',
        })
        step += 1

    train_steps = step

    # ── 測試段（CNN out-of-sample 預測，供 RL 驗證績效）──
    for i in range(len(y_true_test) - 1):
        date_str = pd.Timestamp(test_dates[i]).strftime('%Y-%m-%dT%H:%M:%S') \
                   if i < len(test_dates) else ''
        pred_return = (float(y_pred_test[i + 1]) - float(y_true_test[i])) \
                      / (float(y_true_test[i]) + 1e-9) * 100
        o, h, l = (round(float(test_ohlcv[i, j]), 2) for j in range(3)) \
                  if i < len(test_ohlcv) else (0.0, 0.0, 0.0)
        data.append({
            'step':            step,
            'date':            date_str,
            'open':            o,
            'high':            h,
            'low':             l,
            'price':           round(float(y_true_test[i]), 2),
            'pred_return_pct': round(pred_return, 4),
            'phase':           'test',
            'market':          str(test_market[i]) if i < len(test_market) else 'bull',
        })
        step += 1

    output = {
        'interval':    INTERVAL,
        'window_size': WINDOW_SIZE,
        'total_steps': len(data),
        'train_steps': train_steps,
        'test_steps':  len(data) - train_steps,
        'data':        data,
    }

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    bull_train = sum(1 for d in data[:train_steps] if d['market'] == 'bull')
    bear_train = train_steps - bull_train

    print(f'\n    已匯出 {path}（共 {len(data)} 步）')
    print(f'    訓練段：{train_steps} 步（bull={bull_train}, bear={bear_train}）')
    print(f'    測試段：{len(data) - train_steps} 步（phase=test）')
    print(f'    pred_return_pct 範圍：'
          f'{min(d["pred_return_pct"] for d in data):.2f}% ~ '
          f'{max(d["pred_return_pct"] for d in data):.2f}%')


# ═════════════════════════════════════════════════════════════
# 主程式
# ═════════════════════════════════════════════════════════════

def main():
    sep = '═' * 55
    print(sep)
    print('  BTC/USDT 1D CNN 量化交易回測系統')
    print(sep)

    # 1. 抓資料（yfinance 1h 限制：最近 730 天）
    print('\n[1] 抓取資料（最近 730 天 1h K棒）...')
    df_all = fetch_klines()
    print(f'    原始資料：{len(df_all)} 筆｜'
          f'{df_all.index[0].strftime("%Y-%m-%d")} ~ {df_all.index[-1].strftime("%Y-%m-%d")}')

    # 2. 特徵工程
    print('\n[2] 計算技術指標...')
    df_all = add_features(df_all)

    # 3. 按筆數切割：最後 TEST_HOURS 根為測試集，其餘為訓練集
    #    這樣訓練集 = 較早期資料，測試集 = 最近 30 天，符合老師要求
    print(f'\n[3] 切割｜訓練：較早期資料　測試：最後 {TEST_BARS} 根')
    split_idx = len(df_all) - TEST_BARS
    df_train  = df_all.iloc[:split_idx]
    df_test   = df_all.iloc[split_idx:]
    print(f'    訓練集：{len(df_train)} 筆（{df_train.index[0].strftime("%Y-%m-%d")} ~ {df_train.index[-1].strftime("%Y-%m-%d")}）')
    print(f'    測試集：{len(df_test)} 筆（{df_test.index[0].strftime("%Y-%m-%d")} ~ {df_test.index[-1].strftime("%Y-%m-%d")}）')

    # 4. 正規化（scaler 只 fit 訓練集，避免資料洩漏）
    print('\n[4] 正規化（scaler 只 fit 訓練集）...')
    scaler       = MinMaxScaler()
    train_scaled = scaler.fit_transform(df_train[FEATURE_COLS].values)
    test_scaled  = scaler.transform(df_test[FEATURE_COLS].values)

    X_train, y_train = make_sequences(train_scaled)
    X_test,  y_test  = make_sequences(test_scaled)
    print(f'    訓練序列：{len(X_train)} 筆　測試序列：{len(X_test)} 筆')

    # 5. 訓練
    print('\n[5] 建立 & 訓練 1D CNN...')
    model = build_model(input_shape=(WINDOW_SIZE, len(FEATURE_COLS)))
    model.summary()

    history = model.fit(
        X_train, y_train,
        epochs=EPOCHS,
        batch_size=BATCH_SIZE,
        validation_split=0.1,
        callbacks=[
            keras.callbacks.EarlyStopping(patience=7, restore_best_weights=True),
            keras.callbacks.ReduceLROnPlateau(patience=3, factor=0.5),
        ],
        verbose=1,
    )

    # 6. 預測 & 評估
    print('\n[6] 預測...')
    y_pred_s     = model.predict(X_test,  verbose=0).flatten()
    y_true_price = inverse_close(scaler, y_test)
    y_pred_price = inverse_close(scaler, y_pred_s)

    # 訓練集預測（in-sample，供 RL 訓練段使用）
    y_pred_train_s = model.predict(X_train, verbose=0).flatten()
    y_true_train   = inverse_close(scaler, y_train)
    y_pred_train   = inverse_close(scaler, y_pred_train_s)

    rmse = np.sqrt(mean_squared_error(y_true_price, y_pred_price))
    mae  = mean_absolute_error(y_true_price, y_pred_price)
    mape = np.mean(np.abs((y_true_price - y_pred_price) / (y_true_price + 1e-9))) * 100
    print(f'    RMSE : {rmse:>10.2f} USDT')
    print(f'    MAE  : {mae:>10.2f} USDT')
    print(f'    MAPE : {mape:>10.2f} %')

    # 7. 回測
    print('\n[7] 回測...')
    equity, metrics = backtest(y_true_price, y_pred_price)

    test_start_str = df_test.index[0].strftime('%Y-%m-%d')
    test_end_str   = df_test.index[-1].strftime('%Y-%m-%d')
    print(f'\n{sep}')
    print(f'  回測結果  (Test: {test_start_str} ~ {test_end_str})')
    print(sep)
    print(f'  初始資金   : ${metrics["initial_capital"]:>12,.2f} USDT')
    print(f'  最終資金   : ${metrics["final_capital"]:>12,.2f} USDT')
    print(f'  總報酬率   :  {metrics["total_return"]:>+11.2f} %')
    print(f'  最大回撤   :  {metrics["max_drawdown"]:>11.2f} %')
    print(f'  勝率       :  {metrics["win_rate"]:>11.1f} %')
    print(f'  Sharpe     :  {metrics["sharpe_ratio"]:>11.4f}')
    print(f'  交易次數   :  {metrics["total_trades"]:>11} 次')
    print(sep)

    # 8. [Phase 1] 牛熊標記 + 匯出 btc_states.json
    print('\n[8] 計算牛熊市標記（MA720）...')
    market_labels = label_market(df_all)
    train_dates   = df_train.index[WINDOW_SIZE : WINDOW_SIZE + len(y_true_train)]
    test_dates    = df_test.index[WINDOW_SIZE  : WINDOW_SIZE + len(y_true_price)]
    train_market  = market_labels.reindex(train_dates).fillna('bull').values
    test_market   = market_labels.reindex(test_dates).fillna('bull').values
    train_ohlcv   = df_train.loc[train_dates, ['open', 'high', 'low']].values
    test_ohlcv    = df_test.loc[test_dates,   ['open', 'high', 'low']].values

    print('    匯出 btc_states.json（供 RR 平台 RL 訓練使用）...')
    export_btc_states(train_dates, y_true_train, y_pred_train, train_market, train_ohlcv,
                       test_dates,  y_true_price, y_pred_price, test_market, test_ohlcv)
    print('    ※ state 分類由 btc_trading.html UI 控制，JSON 只含原始漲跌幅')

    # 9. 畫圖並存檔
    print('\n[9] 繪圖並存檔...')
    plot_candlestick(df_all,
                     save_path='candlestick.png')
    plot_prediction(test_dates[:len(y_true_price)], y_true_price, y_pred_price,
                    save_path='prediction.png')
    plot_equity_curve(equity, metrics,
                      save_path='equity_curve.png')
    plot_training_history(history,
                          save_path='training_history.png')

    print('\n完成！btc_states.json 可直接放入 ReinforceLab/games/ 供 Phase 2 使用。')


main()