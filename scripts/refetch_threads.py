#!/usr/bin/env python3
"""Re-fetch download links for specific forum threads (BT seed / feature codes)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from magnet_select import apply_selection
from scan import extract_thread_links, pass_age_gate


def refetch_threads(
    threads: list[dict],
    *,
    output_dir: Path,
    forum_url: str = "https://www.sehuatang.org/forum-142-1.html",
    headless: bool = True,
) -> list[dict]:
    out_dir = output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    profile = out_dir / "chrome_profile"

    results: list[dict] = []
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(profile),
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        )
        page = context.new_page()
        # Warm up forum session (helps Cloudflare + age gate)
        try:
            page.goto(forum_url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(8000)
            pass_age_gate(page)
            page.wait_for_timeout(2000)
            if "Just a moment" in page.content():
                print("[warn] Cloudflare challenge on forum list — try --no-headless locally")
        except Exception as exc:
            print(f"[warn] forum warmup failed: {exc}")

        for i, thread in enumerate(threads, 1):
            href = thread.get("href", "")
            title = thread.get("title", "")
            item = dict(thread)
            print(f"[{i}/{len(threads)}] {href} {title[:60]}")
            if not href:
                results.append(item)
                continue
            links = extract_thread_links(page, href, forum_url)
            item.update(links)
            apply_selection(item, javdb_client=None)
            m = len(item.get("magnets") or [])
            e = len(item.get("ed2k") or [])
            h = len(item.get("hash_entries") or [])
            dl = item.get("selected_download") or item.get("selected_magnet") or ""
            print(f"  -> magnets={m} ed2k={e} hash_entries={h} selected={'yes' if dl else 'no'}")
            if dl:
                print(f"     {str(dl)[:80]}")
            results.append(item)
        context.close()
    return results


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Re-fetch links for specific forum threads")
    parser.add_argument("--input", required=True, help="JSON file with [{href, title, ...}]")
    parser.add_argument("--output-dir", default=".", help="Output dir (chrome profile + results)")
    parser.add_argument("--output-json", default="refetch_result.json", help="Result filename")
    parser.add_argument("--forum-url", default="https://www.sehuatang.org/forum-142-1.html")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--no-headless", action="store_true")
    args = parser.parse_args()
    if args.no_headless:
        args.headless = False

    threads = json.loads(Path(args.input).read_text(encoding="utf-8"))
    results = refetch_threads(
        threads,
        output_dir=Path(args.output_dir),
        forum_url=args.forum_url,
        headless=args.headless,
    )

    out_path = Path(args.output_dir) / args.output_json
    summary = {
        "total": len(results),
        "with_magnets": sum(1 for x in results if x.get("magnets")),
        "with_hash_entries": sum(1 for x in results if x.get("hash_entries")),
        "with_selected": sum(1 for x in results if x.get("selected_download") or x.get("selected_magnet")),
        "threads": results,
    }
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[done] {summary['with_selected']}/{summary['total']} with selected download")
    print(f"[done] saved to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
