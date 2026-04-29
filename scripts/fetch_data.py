"""
TradeTrail 資料預處理腳本
用途：從 yfinance 抓取美股歷史 OHLCV，計算技術指標，輸出靜態 JSON
執行：python scripts/fetch_data.py
輸出：data/<symbol>.json（每個標的一個檔案）
"""

import json
import os
import warnings
warnings.filterwarnings('ignore')

import yfinance as yf
import pandas as pd
import numpy as np

# ── 設定區 ───────────────────────────────────────────────
SYMBOLS = [
    'SPY',   # S&P 500 ETF — 市場基準
    'QQQ',   # Nasdaq 100 ETF — 科技指數
    'AAPL',  # Apple — 穩定大型股
    'NVDA',  # Nvidia — 高波動成長股
    'TSLA',  # Tesla — 超高波動
]
INTERVAL   = '1d'   # 日K，可取得完整歷史
TEST_BARS  = 252    # 測試集保留最後 N 根（1d×252 ≈ 1年）
START_DATE = '2015-01-01'  # 訓練起始日（約 10 年）
OUTPUT_DIR = 'data'
# ────────────────────────────────────────────────────────


def fetch_ohlcv(symbol, interval, start_date):
    df = yf.download(symbol, start=start_date, interval=interval,
                     auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [c.lower() for c in df.columns]
    df.index.name = 'date'
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df = df[['open', 'high', 'low', 'close', 'volume']].copy()
    df.sort_index(inplace=True)
    return df


def add_indicators(df):
    df = df.copy()

    # 移動平均（價格）
    df['ma5']  = df['close'].rolling(5).mean()
    df['ma10'] = df['close'].rolling(10).mean()
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()

    # 成交量均線
    df['vol_ma5'] = df['volume'].rolling(5).mean()

    # RSI-14
    delta = df['close'].diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    df['rsi'] = 100 - 100 / (1 + gain / (loss + 1e-9))

    # KD（Stochastic，14/3/3）
    low14  = df['low'].rolling(14).min()
    high14 = df['high'].rolling(14).max()
    df['stoch_k'] = (df['close'] - low14) / (high14 - low14 + 1e-9) * 100
    df['stoch_d'] = df['stoch_k'].rolling(3).mean()

    # MACD（12/26/9）
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd']        = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()

    # 布林通道（20/2）
    rolling_mean = df['close'].rolling(20).mean()
    rolling_std  = df['close'].rolling(20).std()
    df['boll_upper'] = rolling_mean + 2 * rolling_std
    df['boll_lower'] = rolling_mean - 2 * rolling_std

    df.dropna(inplace=True)
    return df


def label_market(df):
    """MA20 以上為牛市，以下為熊市"""
    labels = pd.Series('bear', index=df.index)
    labels[df['close'] >= df['ma20']] = 'bull'
    return labels


def to_records(df, market, phase_series):
    records = []
    for i, (idx, row) in enumerate(df.iterrows()):
        records.append({
            'step':         i,
            'date':         idx.strftime('%Y-%m-%dT%H:%M:%S'),
            'open':         round(float(row['open']),         2),
            'high':         round(float(row['high']),         2),
            'low':          round(float(row['low']),          2),
            'close':        round(float(row['close']),        2),
            'volume':       round(float(row['volume']),       0),
            'ma5':          round(float(row['ma5']),          2),
            'ma10':         round(float(row['ma10']),         2),
            'ma20':         round(float(row['ma20']),         2),
            'ma60':         round(float(row['ma60']),         2),
            'vol_ma5':      round(float(row['vol_ma5']),      0),
            'rsi':          round(float(row['rsi']),          2),
            'stoch_k':      round(float(row['stoch_k']),      2),
            'stoch_d':      round(float(row['stoch_d']),      2),
            'macd':         round(float(row['macd']),         4),
            'macd_signal':  round(float(row['macd_signal']),  4),
            'boll_upper':   round(float(row['boll_upper']),   2),
            'boll_lower':   round(float(row['boll_lower']),   2),
            'market':       market.iloc[i],
            'phase':        phase_series.iloc[i],
        })
    return records


def process_symbol(symbol):
    print(f'\n── {symbol} ──')
    print(f'  [1] 抓取 {INTERVAL} 資料（{START_DATE} 起）...')
    df = fetch_ohlcv(symbol, INTERVAL, START_DATE)
    print(f'      原始：{len(df)} 筆 | {df.index[0].date()} ~ {df.index[-1].date()}')

    print('  [2] 計算技術指標...')
    df = add_indicators(df)
    print(f'      處理後：{len(df)} 筆')

    print(f'  [3] 切割（測試集：最後 {TEST_BARS} 根，約 1年）...')
    split    = len(df) - TEST_BARS
    df_train = df.iloc[:split]
    df_test  = df.iloc[split:]
    print(f'      訓練：{len(df_train)} 筆（{df_train.index[0].date()} ~ {df_train.index[-1].date()}）')
    print(f'      測試：{len(df_test)} 筆（{df_test.index[0].date()} ~ {df_test.index[-1].date()}）')

    market_all  = label_market(df)
    phase_train = pd.Series(['train'] * len(df_train), index=df_train.index)
    phase_test  = pd.Series(['test']  * len(df_test),  index=df_test.index)

    records_train = to_records(df_train, market_all.reindex(df_train.index), phase_train)
    records_test  = to_records(df_test,  market_all.reindex(df_test.index),  phase_test)
    for i, r in enumerate(records_test):
        r['step'] = len(records_train) + i

    all_records = records_train + records_test
    output = {
        'symbol':      symbol,
        'interval':    INTERVAL,
        'total_steps': len(all_records),
        'train_steps': len(records_train),
        'test_steps':  len(records_test),
        'data':        all_records,
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f'{symbol.lower()}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, separators=(',', ':'))

    bull_train = sum(1 for r in records_train if r['market'] == 'bull')
    print(f'  [4] 輸出：{path}')
    print(f'      訓練 bull/bear：{bull_train} / {len(records_train) - bull_train}')


def main():
    print(f'TradeTrail fetch_data.py — {INTERVAL} | 起始：{START_DATE}')
    print(f'標的：{", ".join(SYMBOLS)}')
    for symbol in SYMBOLS:
        try:
            process_symbol(symbol)
        except Exception as e:
            print(f'  [!] {symbol} 失敗：{e}')
    print('\n全部完成。')


if __name__ == '__main__':
    main()
