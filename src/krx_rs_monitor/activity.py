"""Independent end-of-day market screens."""
import argparse
from datetime import date, timedelta
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .models import DataError


def tick_size(price):
    for ceiling, tick in ((2000, 1), (5000, 5), (20000, 10), (50000, 50),
                          (200000, 100), (500000, 500)):
        if price < ceiling:
            return tick
    return 1000


def upper_price(base):
    """KRX two-stage truncation, current KOSPI/KOSDAQ ticks (since 2023)."""
    base = int(base)
    if base <= 0:
        return 0
    width = (base * 3 // 10) // tick_size(base) * tick_size(base)
    price = base + width
    return price // tick_size(price) * tick_size(price)


def select_activity(snapshot):
    required = ['name', 'sector', 'market', 'close', 'base_price', 'volume',
                'turnover_today', 'change_pct', 'is_new_listing']
    if snapshot.empty or snapshot.index.has_duplicates or not set(required).issubset(snapshot.columns):
        raise DataError('Incomplete daily market activity snapshot.')
    numeric = snapshot[['close', 'base_price', 'volume', 'turnover_today', 'change_pct']]
    if not np.isfinite(numeric.to_numpy()).all() or (numeric.drop(columns='change_pct') < 0).any().any():
        raise DataError('Invalid market activity values.')
    result = snapshot.copy()
    result['upper_limit'] = result.base_price.map(upper_price)
    # A new listing's first session has a different price range. Do not apply
    # the ordinary 30% formula to it, even if its return happens to be 30%.
    normal = ~result.is_new_listing.astype(bool)
    result['limit_up'] = normal & (result.base_price > 0) & (result.close == result.upper_limit) & (result.volume > 0)
    result.index.name = 'ticker'
    result = result.reset_index()
    limits = result.loc[result.limit_up].sort_values(['turnover_today', 'ticker'], ascending=[False, True])
    active = result.loc[result.volume >= 10_000_000].sort_values(['volume', 'turnover_today', 'ticker'], ascending=[False, False, True])
    return limits, active


def collect_activity(provider, as_of):
    from .providers.pykrx import request_timeout
    # get_sectors also initializes the logged-in provider API without exposing ID.
    sectors = provider.get_sectors(as_of)
    from pykrx.website.krx.market.wrap import get_market_ohlcv_by_market
    anchor = as_of.strftime('%Y%m%d')
    parts = []
    with request_timeout(provider.timeout):
        for market in ('KOSPI', 'KOSDAQ'):
            names = provider._frame(
                f'{anchor}/universe-{market}',
                lambda m=market: provider.stock.get_market_price_change_by_ticker(anchor, anchor, market=m),
                ['종목명', '시가', '종가'],
            )
            names.index = names.index.astype(str).str.zfill(6)
            names = names.loc[names['종가'] > 0]
            daily = provider._frame(
                f'{anchor}/turnover-{anchor}-{market}',
                lambda m=market: provider.stock.get_market_ohlcv_by_ticker(anchor, market=m),
                ['종가', '거래량', '거래대금', '등락률'],
            )
            daily.index = daily.index.astype(str).str.zfill(6)
            info = provider._frame(f'{anchor}/listing-info-{market}',
                                  lambda m=market: get_market_ohlcv_by_market(m), ['상장일'])
            info.index = info.index.astype(str).str.zfill(6)
            listing_dates = pd.to_datetime(info['상장일']).reindex(names.index)
            if listing_dates.isna().any():
                raise DataError('Listing dates missing; cannot verify limit-up classification.')
            frame = names[['종목명', '시가']].rename(columns={'종목명': 'name', '시가': 'base_price'})
            # In the one-day price-change endpoint, 시가 is BAS_PRC, not opening price.
            frame = frame.join(daily[['종가', '거래량', '거래대금', '등락률']].rename(columns={
                '종가': 'close', '거래량': 'volume', '거래대금': 'turnover_today', '등락률': 'change_pct'}))
            frame['market'] = market
            frame['sector'] = [sectors.get(t, '미분류') for t in frame.index]
            frame['is_new_listing'] = listing_dates.dt.date == as_of
            parts.append(frame)
    return pd.concat(parts)


def build(output, provider=None):
    runs = sorted(output.glob('run-????-??-??.json'))
    if not runs:
        print('No new completed session; retaining published activity lists.')
        return
    path = runs[-1]
    meta = json.loads(path.read_text(encoding='utf-8'))
    if meta.get('status') != 'success':
        raise DataError('Market activity requires a completed run.')
    as_of = date.fromisoformat(meta['as_of'])
    if provider is None:
        from .providers.pykrx import PykrxProvider
        provider = PykrxProvider()
    snapshot = collect_activity(provider, as_of)
    limits, active = select_activity(snapshot)
    for prefix, frame in (('limit-up', limits), ('volume10m', active)):
        target = output / f'{prefix}-{as_of}.csv'
        temporary = target.with_suffix('.tmp')
        frame.to_csv(temporary, index=False, encoding='utf-8-sig', float_format='%.8f')
        temporary.replace(target)
    meta['activity'] = {'limit_up': len(limits), 'volume10m': len(active),
                        'volume_threshold': 10_000_000,
                        'limit_up_rule': 'ordinary 30% closing limit, listing-day exclusions',
                        'listing_day_excluded': int(snapshot.is_new_listing.sum())}
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Market activity {as_of}: limit-up={len(limits)}, volume>=10m={len(active)}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('output'))
    args = parser.parse_args()
    build(args.output)


if __name__ == '__main__':
    main()
