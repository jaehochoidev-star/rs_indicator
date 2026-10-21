"""Inspect the saved provider cache without repeating market downloads."""
import argparse
from pathlib import Path
import pandas as pd
import numpy as np


def diagnose(cache_dir, anchor):
    root = Path(cache_dir) / 'v1-pykrx-1.2.9' / anchor.replace('-', '')
    files = list(root.glob('calendar-*.json'))
    if not files:
        raise RuntimeError(f'Calendar cache not found: {root}')
    calendar = pd.read_json(files[0], orient='table')
    sessions = pd.DatetimeIndex(calendar.index).sort_values()[-61:]
    universes = []
    for market in ('KOSPI', 'KOSDAQ'):
        frame = pd.read_json(root / f'universe-{market}.json', orient='table')
        frame = frame.loc[frame['종가'] > 0, ['종목명']].copy()
        frame.index = frame.index.astype(str).str.zfill(6)
        frame['market'] = market
        universes.append(frame)
    universe = pd.concat(universes)
    values = []
    for day in sessions[-20:]:
        parts = []
        for market in ('KOSPI', 'KOSDAQ'):
            frame = pd.read_json(root / f'turnover-{day:%Y%m%d}-{market}.json', orient='table')
            frame.index = frame.index.astype(str).str.zfill(6)
            parts.append(frame['거래대금'])
        values.append(pd.concat(parts).rename(day))
    turnover = pd.DataFrame(values).reindex(columns=universe.index)
    eligible = []
    for ticker in universe.index:
        paths = list(root.glob(f'adjusted-*-{ticker}.json'))
        if not paths:
            continue
        frame = pd.read_json(paths[0], orient='table')
        prices = frame['종가'].reindex(sessions)
        if (prices.notna() & np.isfinite(prices) & (prices > 0)).all():
            eligible.append(ticker)
    sample = turnover[eligible]
    invalid = sample.isna() | ~np.isfinite(sample) | (sample < 0)
    print(f'DIAG universe={len(universe)} eligible={len(eligible)} bad_cells={int(invalid.sum().sum())}', flush=True)
    records = []
    for ticker in invalid.columns[invalid.any()]:
        dates = invalid.index[invalid[ticker]]
        print(f'DIAG ticker={ticker} name={universe.loc[ticker,"종목명"]} market={universe.loc[ticker,"market"]} dates={list(dates.strftime("%Y-%m-%d"))} values={list(sample.loc[dates,ticker])}', flush=True)
        for day in dates:
            records.append({'ticker':ticker,'name':universe.loc[ticker,'종목명'],'market':universe.loc[ticker,'market'],'date':str(day.date()),'value':sample.loc[day,ticker]})
    Path('output').mkdir(exist_ok=True)
    pd.DataFrame(records).to_csv('output/turnover-diagnostics.csv',index=False,encoding='utf-8-sig')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', required=True)
    parser.add_argument('--cache-dir', default='data/cache')
    args=parser.parse_args()
    diagnose(args.cache_dir,args.date)
