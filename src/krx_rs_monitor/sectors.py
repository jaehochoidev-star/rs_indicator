"""Backfill KRX sector names without repeating price collection."""
import argparse
import csv
from datetime import date, datetime
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from .providers.pykrx import PykrxProvider


def enrich(source: Path, output: Path, provider=None):
    metadata = source / 'latest.json'
    if not metadata.exists():
        print('No published data yet; sectors will be included in the first collection.')
        return
    meta = json.loads(metadata.read_text(encoding='utf-8'))
    if meta.get('status') != 'success':
        raise ValueError('Only a successful run can be enriched.')
    stamp = date.fromisoformat(meta['as_of'])
    tables = {}
    fields = {}
    for prefix in ('ranked', f"top{meta['settings']['top']}"):
        with (source / f'{prefix}-{stamp}.csv').open(encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            fields[prefix] = list(reader.fieldnames)
            tables[prefix] = list(reader)
    if all(row.get('sector') and row['sector'] != '미분류' for row in tables['ranked']):
        print('Published results already include sectors.')
        return
    if provider is None:
        if not os.environ.get('KRX_ID') or not os.environ.get('KRX_PW'):
            raise ValueError('KRX_ID/KRX_PW required for sector enrichment.')
        provider = PykrxProvider()
    sectors = provider.get_sectors(stamp)
    if not sectors:
        raise ValueError('No sector data returned; preserving the published results.')
    output.mkdir(parents=True, exist_ok=True)
    for prefix, rows in tables.items():
        if 'sector' not in fields[prefix]:
            fields[prefix].insert(fields[prefix].index('name'), 'sector')
        for row in rows:
            row['sector'] = sectors.get(row['ticker']) or row.get('sector') or '미분류'
        path = output / f'{prefix}-{stamp}.csv'
        with path.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fields[prefix])
            writer.writeheader()
            writer.writerows(rows)
    meta['sector_source'] = 'KRX industry classification'
    meta['sector_as_of'] = stamp.isoformat()
    meta['sector_enriched_at'] = datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
    (output / f'run-{stamp}.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Sectors added for {sum(r["sector"] != "미분류" for r in tables["ranked"])} ranked stocks.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=Path('docs'))
    parser.add_argument('--output', type=Path, default=Path('output'))
    args = parser.parse_args()
    enrich(args.source, args.output)


if __name__ == '__main__':
    main()
