"""Daily turnover leaders, independent of RS history and screen eligibility."""
import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

from .models import DataError


def leaders(universe, daily, limit=40, *, history=None):
    values = daily.reindex(universe.index)
    if not (np.isfinite(values) & (values >= 0)).all():
        raise DataError('Invalid current-session turnover; cannot publish turnover leaders.')
    result = universe.copy()
    result['turnover_today'] = values
    result.index.name = 'ticker'
    result = result.reset_index().sort_values(
        ['turnover_today', 'ticker'], ascending=[False, True]
    ).head(limit).reset_index(drop=True)
    return add_history(result, history) if history is not None else result



def add_history(frame, history):
    history = history.tail(5)
    if len(history) != 5 or history.index.has_duplicates or not history.index.is_monotonic_increasing:
        raise DataError('Five ascending trading sessions required for turnover history.')
    frame = frame.copy()
    for session, daily in history.iterrows():
        values = daily.reindex(frame.ticker)
        if ((values.notna()) & (~np.isfinite(values) | (values < 0))).any():
            raise DataError('Invalid turnover history.')
        frame[f'turnover_{session.date().isoformat()}'] = values.to_numpy()
    if not np.array_equal(history.iloc[-1].reindex(frame.ticker).to_numpy(), frame.turnover_today.to_numpy()):
        raise DataError('Turnover history must end with the ranking session values.')
    previous = history.iloc[-2].reindex(frame.ticker).to_numpy(dtype=float)
    frame['turnover_change_pct'] = (frame.turnover_today.to_numpy() / np.where(previous > 0, previous, np.nan) - 1) * 100
    return frame


def write_leaders(frame, output, stamp):
    output.mkdir(parents=True, exist_ok=True)
    path = output / f'turnover40-{stamp}.csv'
    temporary = path.with_suffix('.tmp')
    frame.to_csv(temporary, index=False, encoding='utf-8-sig', float_format='%.8f')
    temporary.replace(path)


def backfill(source, output):
    """Fetch just the published session, without recollecting price histories."""
    from .providers.pykrx import PykrxProvider, request_timeout
    meta_path = source / 'latest.json'
    if not meta_path.exists():
        return
    meta = json.loads(meta_path.read_text(encoding='utf-8'))
    stamp = date.fromisoformat(meta['as_of'])
    existing_meta = output / f'run-{stamp}.json'
    if existing_meta.exists():
        meta = json.loads(existing_meta.read_text(encoding='utf-8'))
    provider = PykrxProvider()
    sectors = provider.get_sectors(stamp)
    anchor = stamp.strftime('%Y%m%d')
    parts, values = [], []
    with request_timeout(provider.timeout):
        for market in ('KOSPI', 'KOSDAQ'):
            names = provider._frame(
                f'{anchor}/universe-{market}',
                lambda m=market: provider.stock.get_market_price_change_by_ticker(anchor, anchor, market=m),
                ['종목명', '종가'],
            )
            names = names.loc[names['종가'] > 0, ['종목명']].rename(columns={'종목명': 'name'})
            names.index = names.index.astype(str).str.zfill(6)
            names['market'] = market
            names['sector'] = [sectors.get(t, '미분류') for t in names.index]
            parts.append(names)
            daily = provider._frame(
                f'{anchor}/turnover-{anchor}-{market}',
                lambda m=market: provider.stock.get_market_ohlcv_by_ticker(anchor, market=m),
                ['거래대금'],
            )
            daily.index = daily.index.astype(str).str.zfill(6)
            values.append(daily['거래대금'])
    frame = leaders(pd.concat(parts), pd.concat(values))
    with request_timeout(provider.timeout):
        start = (stamp - timedelta(days=180)).strftime('%Y%m%d')
        calendar = provider._frame(
            f'{anchor}/calendar-{start}',
            lambda: provider.stock.get_index_ohlcv_by_date(start, anchor, '1001'), ['종가'],
        )
        sessions = pd.DatetimeIndex(calendar.index).normalize().sort_values()
        sessions = sessions[sessions.date <= stamp][-5:]
        if len(sessions) != 5 or sessions[-1].date() != stamp:
            raise DataError('Published date does not match the turnover calendar.')
        history = []
        for session in sessions[:-1]:
            day = session.strftime('%Y%m%d')
            daily_parts = []
            for market in ('KOSPI', 'KOSDAQ'):
                daily = provider._frame(
                    f'{anchor}/turnover-{day}-{market}',
                    lambda d=day, m=market: provider.stock.get_market_ohlcv_by_ticker(d, market=m), ['거래대금'],
                )
                daily.index = daily.index.astype(str).str.zfill(6)
                daily_parts.append(daily['거래대금'])
            combined = pd.concat(daily_parts)
            missing = pd.Index(frame.ticker).difference(combined.index)
            if len(missing):
                prior = provider._frame(
                    f'{anchor}/turnover-{day}-KONEX',
                    lambda d=day: provider.stock.get_market_ohlcv_by_ticker(d, market='KONEX'), ['거래대금'],
                )
                prior.index = prior.index.astype(str).str.zfill(6)
                combined = pd.concat([combined, prior.loc[missing.intersection(prior.index), '거래대금']])
            history.append(combined.reindex(frame.ticker).rename(session))
        history.append(frame.set_index('ticker').turnover_today.rename(sessions[-1]))
        frame = add_history(frame, pd.DataFrame(history))
    meta['turnover_sessions'] = [s.date().isoformat() for s in sessions]
    write_leaders(frame, output, stamp)
    for prefix in ('ranked', f"top{meta['settings']['top']}"):
        target = output / f'{prefix}-{stamp}.csv'
        if not target.exists():
            shutil.copyfile(source / target.name, target)
    meta['turnover_displayed'] = len(frame)
    existing_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Daily turnover leaders: {stamp}, {len(frame)} stocks')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=Path('docs'))
    parser.add_argument('--output', type=Path, default=Path('output'))
    args = parser.parse_args()
    backfill(args.source, args.output)


if __name__ == '__main__':
    main()
