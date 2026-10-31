#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Submit magnet links to GuangYaPan cloud offline download."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from guangya_auth import (
    classify_submit_error,
    format_submit_skip_reason,
    load_saved_device_id,
    resolve_access_token,
    resolve_client_id,
    resolve_device_id,
    resolve_refresh_token,
    save_credentials,
)

GUANGYA_V1_UNSUPPORTED_ED2K = "GuangYa v1: ed2k links are not supported (magnet only)"
GUANGYA_V1_UNSUPPORTED_SHA = "GuangYa v1: PikPak feature codes are not supported (magnet only)"


def build_client():
    from guangyaclient import GuangyaClient
    from guangya_auth import sync_credentials_from_skill_store

    sync_credentials_from_skill_store()
    access = resolve_access_token()
    refresh = resolve_refresh_token()
    device_id = resolve_device_id()
    if not device_id:
        from guangyaclient.tools import generate_did

        device_id = generate_did()
        save_credentials(device_id=device_id)
    return GuangyaClient(
        access_token=access or None,
        refresh_token=refresh or None,
        device_id=device_id,
    )


def persist_client_tokens(client) -> None:
    """Write back tokens if the client refreshed them."""
    access = (getattr(client, "token", None) or "").strip()
    refresh = (getattr(client, "refresh_token_value", None) or "").strip()
    device_id = (getattr(client, "device_id", None) or "").strip()
    if not access:
        return
    save_credentials(
        client_id=resolve_client_id(),
        access_token=access,
        refresh_token=refresh or None,
        device_id=device_id or load_saved_device_id() or None,
    )


def is_magnet_uri(uri: str) -> bool:
    return (uri or "").strip().lower().startswith("magnet:")


def prepare_guangya_item(item: dict) -> tuple[dict | None, str | None]:
    """Return (item, None) for submit or (None, error_message) when skipped."""
    if item.get("type") == "sha":
        return None, GUANGYA_V1_UNSUPPORTED_SHA
    uri = (
        item.get("uri")
        or item.get("url")
        or item.get("magnet")
        or ""
    ).strip()
    if uri.lower().startswith("ed2k:"):
        return None, GUANGYA_V1_UNSUPPORTED_ED2K
    if not is_magnet_uri(uri):
        return None, f"GuangYa v1: unsupported link scheme (magnet only): {uri[:80]}"
    out = dict(item)
    out["uri"] = uri
    out["url"] = uri
    out["magnet"] = uri
    out["type"] = "url"
    return out, None


def submit_magnet(
    client,
    url: str,
    *,
    parent_id: str | int | None = None,
) -> dict[str, Any]:
    result = client.cloud_create_task(url, parent_id=parent_id)
    if not isinstance(result, dict):
        return {"raw": result}
    code = result.get("code")
    if code not in (None, 0, "0", 200, "200", "OK", "ok"):
        msg = result.get("message") or result.get("msg") or str(result)
        raise RuntimeError(f"create_task failed: {msg}")
    return result


def submit_one(
    client,
    item: dict,
    *,
    parent_id: str | int | None = None,
) -> dict[str, Any]:
    prepared, err = prepare_guangya_item(item)
    if err:
        raise RuntimeError(err)
    assert prepared is not None
    url = prepared["uri"]
    return submit_magnet(client, url, parent_id=parent_id)


def submit_downloads(
    items: list[dict],
    *,
    folder: str | None = None,
    access_token: str | None = None,
    parent_id: str | int | None = None,
) -> tuple[int, int, list[dict], list[dict], list[dict], str]:
    from guangya_cloud_submit_lib import resolve_guangya_parent_id
    from guangya_folder import guangya_folder_for_download_item, resolve_guangya_folder

    token = resolve_access_token(access_token)
    if not token:
        raise RuntimeError(
            "no GuangYa access token: run `python scripts/guangya_login.py login` "
            "or set GUANGYA_ACCESS_TOKEN"
        )

    fallback_folder = resolve_guangya_folder(folder)
    fixed_parent_id = parent_id if parent_id is not None else _resolve_env_parent_id()
    folder_parent_ids: dict[str, str | int | None] = {}
    logged_folders: set[str] = set()

    def parent_id_for_folder(folder_name: str) -> str | int | None:
        if fixed_parent_id is not None:
            return fixed_parent_id
        if folder_name in folder_parent_ids:
            return folder_parent_ids[folder_name]
        remote_id = resolve_guangya_parent_id(folder_name, create_if_missing=False)
        folder_parent_ids[folder_name] = remote_id
        if folder_name not in logged_folders:
            logged_folders.add(folder_name)
            print(f"[info] guangya folder: {folder_name} ({remote_id})")
        return remote_id

    client = build_client()
    ok = 0
    succeeded: list[dict] = []
    failed: list[dict] = []
    pending: list[dict] = []
    submit_skip_reason = ""

    try:
        for index, item in enumerate(items):
            label = item.get("name") or "download"
            item_folder = guangya_folder_for_download_item(item, fallback=fallback_folder)
            try:
                item_parent_id = parent_id_for_folder(item_folder)
            except RuntimeError as exc:
                err = str(exc)
                print(f"[err] {label}: {err}", file=sys.stderr)
                record = dict(item)
                record.update({"status": "failed", "error": err, "folder": item_folder})
                failed.append(record)
                continue
            try:
                result = submit_one(client, item, parent_id=item_parent_id)
                persist_client_tokens(client)
                task_id = (
                    result.get("taskId")
                    or result.get("task_id")
                    or result.get("id")
                    or (result.get("data") or {}).get("taskId")
                    or "submitted"
                )
                source = item.get("source")
                suffix = f" [{source}]" if source else ""
                print(f"[ok] {label} (magnet){suffix} -> task={task_id}")
                title = (item.get("title") or "")[:80]
                if title:
                    print(f"     {title}")
                record = dict(item)
                record.update(
                    {
                        "status": "ok",
                        "task_id": str(task_id),
                        "phase": "submitted",
                        "folder": item_folder,
                    },
                )
                succeeded.append(record)
                ok += 1
            except Exception as exc:
                err = str(exc)
                print(f"[err] {label} (magnet): {err}", file=sys.stderr)
                record = dict(item)
                record.update({"status": "failed", "error": err})
                failed.append(record)
                error_kind = classify_submit_error(err)
                if error_kind == "auth":
                    submit_skip_reason = format_submit_skip_reason("auth", "invalid")
                    pending.extend(dict(row) for row in items[index + 1 :])
                    print("[warn] guangya auth failed; remaining downloads skipped", file=sys.stderr)
                    break
    finally:
        client.close()

    from pikpak_download import _dedupe_items_by_uri

    pending = _dedupe_items_by_uri(pending)
    return ok, len(items), succeeded, failed, pending, submit_skip_reason


def extract_pending_submit_uris(report: dict) -> list[str]:
    from pikpak_download import item_submit_uri

    uris: list[str] = []
    seen: set[str] = set()

    def add_uri(uri: str) -> None:
        text = (uri or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        uris.append(text)

    skip_reason = (report.get("submit_skip_reason") or "").strip()
    if skip_reason.startswith(("auth", "quota")):
        for item in report.get("pending_submit") or []:
            add_uri(item_submit_uri(item))

    for item in report.get("failed") or []:
        if classify_submit_error(item.get("error") or "") in {"auth", "quota"}:
            add_uri(item_submit_uri(item))

    return uris


def submit_from_result(
    result_path: Path,
    *,
    folder: str | None = None,
    today_only: bool = True,
    region_filter: bool = True,
    new_only: bool = False,
    skip_scan_repeat: bool = True,
    state_file: Path | None = None,
    access_token: str | None = None,
    parent_id: str | int | None = None,
) -> tuple[int, int]:
    from guangya_folder import resolve_guangya_folder
    from download_state import (
        default_state_path,
        filter_new_items,
        load_state,
        mark_submitted,
        save_state,
        touch_run,
    )
    from pikpak_download import load_downloads_from_result, save_download_report

    report_path = result_path.parent / "download_report.json"
    folder_label = resolve_guangya_folder(folder)

    items = load_downloads_from_result(
        result_path,
        today_only=today_only,
        region_filter=region_filter,
    )
    if skip_scan_repeat:
        from scan_delta import filter_new_download_items

        before_scan = len(items)
        items, scan_repeat = filter_new_download_items(items, result_path.parent)
        if scan_repeat:
            print(
                f"[info] scan dedup: skipped {scan_repeat}/{before_scan} download(s) "
                f"already in previous scan",
            )
    state_path = state_file or default_state_path(result_path.parent)
    state = load_state(state_path) if new_only else None
    if new_only and state is not None:
        before = len(items)
        items = filter_new_items(items, state)
        print(f"[info] new-only: {len(items)}/{before} download(s) since last run")
    if not items:
        print("[info] no downloads to submit")
        save_download_report(
            report_path,
            succeeded=[],
            failed=[],
            folder=folder_label,
            source=str(result_path),
        )
        if new_only and state is not None:
            touch_run(state)
            save_state(state_path, state)
        return 0, 0

    token = resolve_access_token(access_token)
    if not token:
        reason = format_submit_skip_reason("auth", "no_token")
        print(f"[err] {reason}: run `python scripts/guangya_login.py login` or set GUANGYA_ACCESS_TOKEN")
        save_download_report(
            report_path,
            succeeded=[],
            failed=[],
            folder=folder_label,
            source=str(result_path),
            pending_submit=items,
            submit_skip_reason=reason,
        )
        print(f"[info] download report: {report_path}")
        if new_only and state is not None:
            touch_run(state)
            save_state(state_path, state)
        return 0, len(items)

    print(f"[info] submitting {len(items)} GuangYa cloud task(s) (magnet-only)...")
    try:
        ok, total, succeeded, failed, pending, submit_skip_reason = submit_downloads(
            items,
            folder=folder,
            access_token=access_token,
            parent_id=parent_id,
        )
    except RuntimeError as exc:
        err = str(exc)
        if classify_submit_error(err) == "auth":
            reason = format_submit_skip_reason("auth", "invalid")
            print(f"[err] guangya auth failed: {err}", file=sys.stderr)
            save_download_report(
                report_path,
                succeeded=[],
                failed=[],
                folder=folder_label,
                source=str(result_path),
                pending_submit=items,
                submit_skip_reason=reason,
            )
            print(f"[info] download report: {report_path}")
            if new_only and state is not None:
                touch_run(state)
                save_state(state_path, state)
            return 0, len(items)
        raise

    if not submit_skip_reason and pending:
        submit_skip_reason = format_submit_skip_reason("auth", "invalid")

    save_download_report(
        report_path,
        succeeded=succeeded,
        failed=failed,
        folder=folder_label,
        source=str(result_path),
        pending_submit=pending or None,
        submit_skip_reason=submit_skip_reason,
    )
    print(f"[info] download report: {report_path}")
    if new_only and state is not None:
        if succeeded:
            mark_submitted(state, succeeded)
        touch_run(state)
        save_state(state_path, state)
    return ok, total


def _resolve_env_parent_id() -> str | int | None:
    """Optional fixed folder id for all submits (overrides region → folder name routing)."""
    raw = (os.environ.get("GUANGYA_PARENT_ID") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return raw


def _resolve_parent_id() -> str | int | None:
    return _resolve_env_parent_id()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Submit magnet links to GuangYaPan offline download",
    )
    parser.add_argument(
        "--magnet",
        action="append",
        default=[],
        help="Magnet URI to submit (repeatable)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Submit all matched items in the result file, not just today's date",
    )
    parser.add_argument(
        "--all-regions",
        action="store_true",
        help="Include western/FC2/amateur (default: 日本有码 + 无码 JAV only)",
    )
    parser.add_argument(
        "--new-only",
        action="store_true",
        help="Skip downloads already submitted in download_state.json",
    )
    parser.add_argument(
        "--state-file",
        default=None,
        help="Path to download state JSON (default: beside result file)",
    )
    args = parser.parse_args()

    parent_id = _resolve_parent_id()

    if args.magnet:
        items = [
            {
                "type": "url",
                "name": f"magnet-{i + 1}",
                "url": m,
                "uri": m,
                "magnet": m,
                "title": m[:80],
                "source": "cli_magnet",
            }
            for i, m in enumerate(args.magnet)
            if (m or "").strip()
        ]
        if not items:
            print("[err] no magnet URIs provided", file=sys.stderr)
            return 1
        try:
            ok, total, _, _, _, _ = submit_downloads(items, parent_id=parent_id)
        except RuntimeError as exc:
            print(f"[err] {exc}", file=sys.stderr)
            return 1
        print(f"\n[done] {ok}/{total} submitted")
        return 0 if ok == total else 1

    result_path = Path(os.environ.get("RESULT_JSON", "last_result.json"))
    if not result_path.exists():
        print(f"[err] result file not found: {result_path}", file=sys.stderr)
        return 1

    try:
        state_file = Path(args.state_file) if args.state_file else None
        ok, total = submit_from_result(
            result_path,
            today_only=not args.all,
            region_filter=not args.all_regions,
            new_only=args.new_only,
            state_file=state_file,
            parent_id=parent_id,
        )
    except RuntimeError as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 1

    print(f"\n[done] {ok}/{total} submitted")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
