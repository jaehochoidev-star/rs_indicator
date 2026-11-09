"""Daily turnover leaders, independent of RS history and screen eligibility."""
import argparse
from datetime import date
import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

from .models import DataError


def leaders(universe, daily, limit=40):
    values = daily.reindex(universe.index)
    if not (np.isfinite(values) & (values >= 0)).all():
        raise DataError('Invalid current-session turnover; cannot publish turnover leaders.')
    result = universe.copy()
    result['turnover_today'] = values
    result.index.name = 'ticker'
    return result.reset_index().sort_values(
        ['turnover_today', 'ticker'], ascending=[False, True]
    ).head(limit).reset_index(drop=True)


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
