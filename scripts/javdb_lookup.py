#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Look up JavDB metadata and magnets by AV number."""
from __future__ import annotations

import argparse
import json
import sys

from javdb_client import JavDBClient, build_query_report, extract_av_number


def print_lookup_result(item: dict) -> None:
    if item.get("error"):
        print(f"{item['number']}: ERROR {item['error']}")
        return
    q = item.get("query") or {}
    label = q.get("content_type_label") or "?"
    print(f"{item['number']} [{label}] ({q.get('release_date', '?')})")
    if q.get("title"):
        print(f"  title: {q['title']}")
    if q.get("score") is not None:
        print(f"  score: {q['score']:.2f}")
    if q.get("cnsub_label"):
        print(f"  cnsub: {q['cnsub_label']}")
    print(f"  query: {q.get('summary', '')}")
    magnets = item.get("magnets") or []
    if magnets:
        for mg in magnets:
            print(f"  magnet: {mg}")
    elif q.get("magnet_status") == "empty":
        print("  magnet: (none on JavDB)")


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
            info = client.lookup(
                number,
                fetch_magnets=args.magnets or True,
                cnsub=args.cnsub,
                hd=args.hd,
                best_only=args.best,
            )
            query = build_query_report(info)
            entry = {
                "number": query.get("number"),
                "query": query,
                "magnets": info.get("magnets") or [],
            }
            results.append(entry)
        except Exception as exc:
            results.append({"number": number, "error": str(exc)})

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    for item in results:
        print_lookup_result(item)
        print()


if __name__ == "__main__":
    main()
