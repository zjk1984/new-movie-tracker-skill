#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Two-phase parallel forum scan: list pages first, enrich threads second."""
from __future__ import annotations

import copy
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from forum_browser import pass_age_gate
from scan import (
    dedupe_candidates,
    enrich_matched_post,
    find_chrome,
    list_forum_pages,
    maybe_send_feishu_progress,
    prepare_scrape_setup,
    save_scan_results,
    scan_log,
)

BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _browser_launch_kwargs(chrome: str, *, headless: bool) -> dict:
    return {
        "executable_path": chrome,
        "headless": headless,
        "args": BROWSER_ARGS,
    }


def _context_kwargs() -> dict:
    return {
        "viewport": {"width": 1366, "height": 768},
        "user_agent": USER_AGENT,
    }


def staging_dir(output_dir: Path) -> Path:
    path = output_dir / "scan_staging"
    path.mkdir(parents=True, exist_ok=True)
    return path


def bootstrap_storage_state(
    output_dir: Path,
    args,
    chrome: str,
    first_forum_url: str,
) -> Path:
    """Use persistent profile once, export cookies for parallel workers."""
    state_path = staging_dir(output_dir) / "storage_state.json"
    user_data_dir = output_dir / "chrome_profile"
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            **_browser_launch_kwargs(chrome, headless=args.headless),
            **_context_kwargs(),
        )
        page = context.new_page()
        try:
            page.goto(first_forum_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            pass_age_gate(page)
            context.storage_state(path=str(state_path))
            scan_log(f"[info] exported browser storage state: {state_path}")
        finally:
            context.close()
    return state_path


def _new_worker_page(playwright, chrome: str, args, storage_state: Path):
    browser = playwright.chromium.launch(
        **_browser_launch_kwargs(chrome, headless=args.headless),
    )
    context = browser.new_context(
        storage_state=str(storage_state),
        **_context_kwargs(),
    )
    page = context.new_page()
    return browser, context, page


def _list_forum_worker(
    forum_url: str,
    args,
    match_ctx,
    storage_state: Path,
    chrome: str,
    screenshot_dir: Path,
):
    with sync_playwright() as playwright:
        browser, context, page = _new_worker_page(
            playwright, chrome, args, storage_state,
        )
        try:
            return list_forum_pages(
                page, forum_url, args, match_ctx, screenshot_dir,
            )
        finally:
            context.close()
            browser.close()


def _enrich_worker(
    item: dict,
    args,
    storage_state: Path,
    chrome: str,
):
    item = copy.deepcopy(item)
    with sync_playwright() as playwright:
        browser, context, page = _new_worker_page(
            playwright, chrome, args, storage_state,
        )
        try:
            javdb_client = None
            if (
                getattr(args, "javdb", False)
                or getattr(args, "javdb_magnets", False)
                or getattr(args, "cnsub_priority", False)
                or getattr(args, "javdb_query", True)
            ):
                from javdb_client import JavDBClient

                javdb_client = JavDBClient(host=getattr(args, "javdb_host", None))
            if args.fetch_magnets and item.get("href"):
                enrich_matched_post(page, item, args, javdb_client)
            elif javdb_client:
                from scan import apply_item_filters, enrich_with_javdb

                scan_log(f"[info] javdb lookup: {item['title'][:40]}...")
                enrich_with_javdb(item, javdb_client, args)
                apply_item_filters(item, javdb_client, args)
            return item
        finally:
            context.close()
            browser.close()


def _send_feishu_start(args) -> None:
    if not getattr(args, "feishu_progress", False):
        return
    try:
        from feishu_notify import is_configured, send_scan_start

        if not is_configured():
            return
        start_page = max(1, getattr(args, "start_page", 1) or 1)
        send_scan_start(
            run_label=getattr(args, "run_label", None) or "scan",
            forum_urls=list(args.urls),
            start_page=start_page,
            max_pages=args.max_pages,
            days=args.days,
            no_date_filter=bool(getattr(args, "no_date_filter", False)),
        )
        scan_log("[ok] feishu start card sent")
    except Exception as exc:
        scan_log(f"[warn] feishu start card: {exc}")


def scrape_two_phase(args) -> None:
    actors, match_names, _javdb_client, match_ctx, cutoff, today, since, until = (
        prepare_scrape_setup(args)
    )
    chrome = find_chrome()
    if not chrome:
        scan_log("[err] chrome not found")
        raise SystemExit(1)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    screenshot_dir = out_dir / "screenshots"
    screenshot_dir.mkdir(exist_ok=True)
    staging = staging_dir(out_dir)

    list_workers = max(1, int(getattr(args, "list_workers", 3) or 3))
    fetch_workers = max(1, int(getattr(args, "fetch_workers", 4) or 4))
    scan_log(
        f"[info] two-phase scan: {len(args.urls)} forums, "
        f"list_workers={list_workers}, fetch_workers={fetch_workers}",
    )

    _send_feishu_start(args)
    storage_state = bootstrap_storage_state(out_dir, args, chrome, args.urls[0])

    scan_log("[info] phase 1: parallel forum list scan")
    forum_results = []
    with ThreadPoolExecutor(max_workers=min(list_workers, len(args.urls))) as pool:
        futures = {
            pool.submit(
                _list_forum_worker,
                forum_url,
                args,
                match_ctx,
                storage_state,
                chrome,
                screenshot_dir,
            ): forum_url
            for forum_url in args.urls
        }
        for future in as_completed(futures):
            forum_url = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                scan_log(f"[err] phase 1 failed for {forum_url}: {exc}")
                raise
            forum_results.append(result)
            if result.stopped == "abort":
                scan_log("[err] cloudflare abort during phase 1")
                raise SystemExit(1)

    candidates: list[dict] = []
    total_posts = 0
    total_pages_scanned = 0
    for result in forum_results:
        candidates.extend(result.candidates)
        total_posts += result.total_posts
        total_pages_scanned += result.pages_scanned

    candidates = dedupe_candidates(candidates)
    candidates_path = staging / "candidates.json"
    candidates_path.write_text(
        json.dumps(
            {
                "forums": len(args.urls),
                "candidates": candidates,
                "total_posts": total_posts,
                "pages_scanned": total_pages_scanned,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    scan_log(
        f"[info] phase 1 done: {len(candidates)} candidates, "
        f"{total_pages_scanned} pages, saved {candidates_path}",
    )

    feishu_progress_sent = 0
    feishu_progress_sent = maybe_send_feishu_progress(
        len(candidates),
        feishu_progress_sent,
        args,
        phase=" (phase 1)",
    )

    all_matched: list[dict] = []
    if args.fetch_magnets:
        enrich_items = [item for item in candidates if item.get("href")]
        no_href = [item for item in candidates if not item.get("href")]
        scan_log(
            f"[info] phase 2: parallel thread enrich for {len(enrich_items)} posts",
        )
        enriched_by_key: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=fetch_workers) as pool:
            futures = {
                pool.submit(_enrich_worker, item, args, storage_state, chrome): item
                for item in enrich_items
            }
            done = 0
            for future in as_completed(futures):
                source = futures[future]
                item = future.result()
                key = (source.get("href") or "").strip() or source.get("title", "")
                enriched_by_key[key] = item
                done += 1
                feishu_progress_sent = maybe_send_feishu_progress(
                    done,
                    feishu_progress_sent,
                    args,
                    phase=" (phase 2)",
                )
        for item in no_href:
            enriched_by_key[item.get("title", "")] = _enrich_worker(
                item, args, storage_state, chrome,
            )
        for item in candidates:
            key = (item.get("href") or "").strip() or item.get("title", "")
            all_matched.append(enriched_by_key.get(key, item))
    else:
        all_matched = candidates

    scan_log(f"[info] phase 2 done: enriched {len(all_matched)} matched posts")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            **_browser_launch_kwargs(chrome, headless=args.headless),
        )
        context = browser.new_context(
            storage_state=str(storage_state),
            **_context_kwargs(),
        )
        page = context.new_page()
        try:
            save_scan_results(
                args,
                out_dir,
                all_matched,
                total_posts=total_posts,
                total_pages_scanned=total_pages_scanned,
                cutoff=cutoff,
                today=today,
                actors=actors,
                match_names=match_names,
                since=since,
                until=until,
                page=page,
                screenshot_dir=screenshot_dir,
                num_forums=len(args.urls),
            )
        except PlaywrightTimeout:
            scan_log("[err] page timeout while saving results")
            page.screenshot(path=str(screenshot_dir / "timeout.png"))
        finally:
            context.close()
            browser.close()
