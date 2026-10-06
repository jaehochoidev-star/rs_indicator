import argparse
from dataclasses import asdict
from datetime import date, datetime, timedelta
import json
import getpass
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

from .models import DataError, MarketDataProvider, NoTradingSession
from .scoring import ScreenConfig, score


def resolve_date(explicit: str | None, now: datetime) -> date:
    now = now.astimezone(ZoneInfo("Asia/Seoul"))
    latest = now.date() if now.hour >= 18 else now.date() - timedelta(days=1)
    if explicit:
        requested = date.fromisoformat(explicit)
        if requested > latest:
            raise ValueError("Use a completed date (today is accepted after 18:00 Asia/Seoul).")
        return requested
    return latest


def run(provider: MarketDataProvider, requested: date, config: ScreenConfig, output: Path):
    data = provider.collect(requested)
    ranked, top, stats = score(data, config)
    output.mkdir(parents=True, exist_ok=True)
    stamp = data.as_of.isoformat()
    for name, frame in (("ranked", ranked), ("top20", top)):
        path = output / f"{name}-{stamp}.csv"
        temporary = path.with_suffix(".tmp")
        frame.to_csv(temporary, index=False, encoding="utf-8-sig", float_format="%.8f")
        temporary.replace(path)
    metadata = {
        "status": "success", "provider": type(provider).__name__,
        "requested_date": requested.isoformat(), "as_of": stamp,
        "generated_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
        "settings": asdict(config), "statistics": stats,
        "percentile": "average rank / eligible combined universe size * 100",
        "price_basis": "adjusted closes", "turnover_currency": "KRW",
        "average_includes_as_of": True,
    }
    path = output / f"run-{stamp}.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    print(f"\nAs of {stamp} | universe={stats['universe']} eligible={stats['eligible']} "
          f"excluded={stats['excluded_short_or_invalid_history']} matched={stats['matched']}")
    if top.empty:
        print("No stocks meet all conditions.")
    else:
        display = top[["ticker", "name", "market", "RS1", "RS5", "RS20", "RS60", "RS_Score"]].copy()
        display["avg20_억원"] = top.turnover_20d_avg / 100_000_000
        display["today_억원"] = top.turnover_today / 100_000_000
        print(display.to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    print(f"Results: {output.resolve()}")
    return metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description="KOSPI + KOSDAQ RS TOP20 monitor")
    parser.add_argument("--date", help="YYYY-MM-DD; weekend/holiday uses the preceding session")
    parser.add_argument("--weights", nargs=4, type=float, default=(10, 30, 40, 20), metavar=("RS1", "RS5", "RS20", "RS60"))
    parser.add_argument("--avg-turnover", type=float, default=5_000_000_000, help="KRW")
    parser.add_argument("--today-turnover", type=float, default=10_000_000_000, help="KRW")
    parser.add_argument("--rs20-min", type=float, default=90)
    parser.add_argument("--rs5-min", type=float, default=90)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--cache-dir", type=Path, default=Path("data/cache"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--login", action="store_true", help="Prompt for KRX credentials for this process only")
    parser.add_argument("--skip-nontrading", action="store_true", help="Skip holidays without republishing old data")
    args = parser.parse_args(argv)
    try:
        config = ScreenConfig(tuple(args.weights), args.avg_turnover, args.today_turnover,
                              args.rs20_min, args.rs5_min, args.top)
        requested = resolve_date(args.date, datetime.now(ZoneInfo("Asia/Seoul")))
        if args.login:
            os.environ["KRX_ID"] = input("KRX ID: ").strip()
            os.environ["KRX_PW"] = getpass.getpass("KRX password (hidden): ")
        if not os.environ.get("KRX_ID") or not os.environ.get("KRX_PW"):
            raise DataError("KRX_ID/KRX_PW are not set. Run with --login in a terminal, "
                            "or configure environment variables / GitHub Actions Secrets.")
        from .providers.pykrx import PykrxProvider
        provider = PykrxProvider(args.cache_dir, timeout=args.timeout, refresh=args.refresh,
                                 skip_nontrading=args.skip_nontrading,
                                 progress=lambda message: print(message, flush=True))
        run(provider, requested, config, args.output_dir)
        return 0
    except NoTradingSession as exc:
        print(str(exc))
        return 0
    except (DataError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (EOFError, KeyboardInterrupt):
        print("Cancelled.", file=sys.stderr)
        return 130
