#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Look up JavDB metadata and magnets by AV number."""
from __future__ import annotations

import argparse
import json
import sys

from javdb_client import JavDBClient, extract_av_number


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Look up JavDB metadata and magnets")
    parser.add_argument("numbers", nargs="+", help="AV numbers or text containing numbers")
    parser.add_argument("--host", default=None, help="JavDB API host (default: mirror)")
    parser.add_argument("--magnets", action="store_true", help="Fetch magnet links")
    parser.add_argument("--best", action="store_true", help="Only output the best magnet")
    parser.add_argument("--cnsub", action="store_true", help="Filter magnets with Chinese subtitles")
    parser.add_argument("--hd", action="store_true", help="Filter HD magnets")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    client = JavDBClient(host=args.host)
    results = []
    for raw in args.numbers:
        number = extract_av_number(raw) or raw.strip().upper()
        try:
            item = client.lookup(
                number,
                fetch_magnets=args.magnets,
                cnsub=args.cnsub,
                hd=args.hd,
                best_only=args.best,
            )
            item.pop("magnet_rows", None)
            results.append(item)
        except Exception as exc:
            results.append({"number": number, "error": str(exc)})

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    for item in results:
        if item.get("error"):
            print(f"{item['number']}: ERROR {item['error']}")
            continue
        print(f"{item['number']} ({item.get('release_date', '?')})")
        if item.get("title"):
            print(f"  title: {item['title']}")
        if args.magnets:
            magnets = item.get("magnets") or []
            if magnets:
                for mg in magnets:
                    print(f"  magnet: {mg}")
            else:
                print("  magnet: (none)")


if __name__ == "__main__":
    main()
