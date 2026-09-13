#!/usr/bin/env python3
"""Submit magnet links to PikPak cloud download via API."""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import requests

DEFAULT_FOLDER = "My Pack"

CLIENT_ID = "YUMx5nI8ZU8Ap8pm"
CLIENT_VERSION = "1.0.0"
PACKAGE_NAME = "mypikpak.com"
DRIVE_HOST = "https://api-drive.mypikpak.com"
USER_HOST = "https://user.mypikpak.com"

ALGO_OBJECTS = [
    {"alg": "md5", "salt": "mg3UtlOJ5/6WjxHsGXtAthe"},
    {"alg": "md5", "salt": "kRG2RIlL/eScz3oDbzeF1"},
    {"alg": "md5", "salt": "uOIOBDcR5QALlRUUK4JVoreEI0i3RG8ZiUf2hMOH"},
    {"alg": "md5", "salt": "wa+0OkzHAzpyZ0S/JAnHmF2BlMR9Y"},
    {"alg": "md5", "salt": "ZWV2OkSLoNkmbr58v0f6U3udtqUNP7XON"},
    {"alg": "md5", "salt": "Jg4cDxtvbmlakZIOpQN0oY1P0eYkA4xquMY9/xqwZE5sjrcHwufR"},
    {"alg": "md5", "salt": "XHfs"},
    {"alg": "md5", "salt": "S4/mRgYpWyNGEUxVsYBw8n//zlywe5Ga1R8ffWJSOPZnMqWb4w"},
]

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def decode_jwt_payload(token: str) -> dict:
    import base64

    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def captcha_sign(device_id: str) -> tuple[str, str]:
    ts = str(int(time.time() * 1000))
    sign = CLIENT_ID + CLIENT_VERSION + PACKAGE_NAME + device_id + ts
    for algo in ALGO_OBJECTS:
        sign = hashlib.md5((sign + algo["salt"]).encode()).hexdigest()
    return "1." + sign, ts


def get_captcha_token(session: requests.Session, device_id: str, user_id: str, action: str) -> str:
    captcha_sign_val, ts = captcha_sign(device_id)
    body = {
        "action": action,
        "client_id": CLIENT_ID,
        "device_id": device_id,
        "meta": {
            "captcha_sign": captcha_sign_val,
            "client_version": CLIENT_VERSION,
            "package_name": PACKAGE_NAME,
            "timestamp": ts,
            "user_id": user_id,
        },
        "redirect_uri": "https://api.mypikpak.com/v1/auth/callback",
    }
    resp = session.post(
        f"{USER_HOST}/v1/shield/captcha/init",
        params={"client_id": CLIENT_ID},
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("captcha_token")
    if not token:
        raise RuntimeError(f"captcha init failed: {data}")
    return token


def api_headers(access_token: str, device_id: str, captcha_token: str | None = None) -> dict:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": UA,
        "x-device-id": device_id,
        "Content-Type": "application/json",
    }
    if captcha_token:
        headers["x-captcha-token"] = captcha_token
    return headers


def list_files(
    session: requests.Session,
    access_token: str,
    device_id: str,
    user_id: str,
    parent_id: str = "",
    limit: int = 200,
) -> list[dict]:
    filters = json.dumps(
        {"phase": {"eq": "PHASE_TYPE_COMPLETE"}, "trashed": {"eq": False}},
        separators=(",", ":"),
    )
    params = {
        "parent_id": parent_id,
        "thumbnail_size": "SIZE_MEDIUM",
        "limit": str(limit),
        "with_audit": "true",
        "filters": filters,
    }
    captcha_token = get_captcha_token(session, device_id, user_id, "GET:/drive/v1/files/")
    resp = session.get(
        f"{DRIVE_HOST}/drive/v1/files",
        headers=api_headers(access_token, device_id, captcha_token),
        params=params,
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"list files failed: HTTP {resp.status_code} {resp.text[:300]}")
    return resp.json().get("files") or []


def find_folder_id(
    session: requests.Session,
    access_token: str,
    device_id: str,
    user_id: str,
    folder_name: str,
) -> str | None:
    for item in list_files(session, access_token, device_id, user_id):
        if item.get("kind") == "drive#folder" and item.get("name") == folder_name:
            return item.get("id")
    return None


def offline_download(
    session: requests.Session,
    access_token: str,
    device_id: str,
    user_id: str,
    name: str,
    magnet: str,
    parent_id: str | None = None,
) -> dict:
    body = {
        "kind": "drive#file",
        "name": name,
        "upload_type": "UPLOAD_TYPE_URL",
        "url": {"url": magnet},
    }
    if parent_id:
        body["parent_id"] = parent_id
        body["folder_type"] = ""
    else:
        body["folder_type"] = "DOWNLOAD"
    captcha_token = get_captcha_token(session, device_id, user_id, "POST:/drive/v1/files")
    resp = session.post(
        f"{DRIVE_HOST}/drive/v1/files",
        headers=api_headers(access_token, device_id, captcha_token),
        json=body,
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"{name}: HTTP {resp.status_code} {resp.text[:500]}")
    return resp.json()


def pick_item_magnet(item: dict) -> str | None:
    selected = (item.get("selected_magnet") or "").strip()
    if selected:
        return selected
    magnets = item.get("magnets") or []
    return magnets[0] if magnets else None


def item_download_name(item: dict) -> str:
    for key in ("av_number",):
        value = item.get(key)
        if value:
            return str(value)
    title = item.get("title", "download")
    return title.split()[0] if title else "download"


def load_magnets_from_result(
    result_path: Path,
    *,
    today_only: bool = True,
    region_filter: bool = True,
) -> list[dict]:
    import sys

    sys.path.insert(0, str(Path(__file__).parent))
    from content_filter import is_downloadable

    data = json.loads(result_path.read_text(encoding="utf-8"))
    today = data.get("today") or data.get("scan_time", "")[:10]
    items = []
    for item in data.get("matched", []):
        if today_only and item.get("date") != today:
            continue
        if region_filter and not is_downloadable(item):
            continue
        magnet = pick_item_magnet(item)
        if not magnet:
            continue
        title = item.get("title", "download")
        items.append({
            "name": item_download_name(item),
            "title": title,
            "magnet": magnet,
            "source": item.get("magnet_source", ""),
            "href": item.get("href", ""),
            "av_number": item.get("av_number", ""),
        })
    return items


def load_today_magnets(result_path: Path) -> list[dict]:
    return load_magnets_from_result(result_path, today_only=True)


def submit_magnets(
    items: list[dict],
    *,
    folder: str = DEFAULT_FOLDER,
    access_token: str | None = None,
) -> tuple[int, int, list[dict]]:
    from pikpak_auth import resolve_folder, resolve_token

    token = resolve_token(access_token)
    if not token:
        raise RuntimeError(
            "no PikPak token: run `python scripts/pikpak_login.py login` "
            "or set PIKPAK_TOKEN"
        )
    folder = resolve_folder(folder, DEFAULT_FOLDER)

    payload = decode_jwt_payload(token)
    user_id = payload.get("sub", "")
    device_id = hashlib.md5(user_id.encode()).hexdigest()
    session = requests.Session()
    parent_id = find_folder_id(session, token, device_id, user_id, folder)
    if parent_id:
        print(f"[info] download folder: {folder} ({parent_id})")
    else:
        print(f"[warn] folder '{folder}' not found, using folder_type=DOWNLOAD fallback")

    ok = 0
    succeeded: list[dict] = []
    for item in items:
        try:
            result = offline_download(
                session,
                token,
                device_id,
                user_id,
                item["name"],
                item["magnet"],
                parent_id=parent_id,
            )
            task = result.get("task") or {}
            file_info = result.get("file") or {}
            task_id = task.get("id") or file_info.get("id") or "unknown"
            phase = task.get("phase") or file_info.get("phase") or "submitted"
            source = item.get("source")
            suffix = f" [{source}]" if source else ""
            print(f"[ok] {item['name']}{suffix} -> task={task_id} phase={phase}")
            print(f"     {item['title'][:80]}")
            ok += 1
            succeeded.append(item)
        except Exception as exc:
            print(f"[err] {item['name']}: {exc}", file=sys.stderr)
    return ok, len(items), succeeded


def submit_from_result(
    result_path: Path,
    *,
    folder: str = DEFAULT_FOLDER,
    today_only: bool = True,
    region_filter: bool = True,
    new_only: bool = False,
    state_file: Path | None = None,
    access_token: str | None = None,
) -> tuple[int, int]:
    from download_state import (
        default_state_path,
        filter_new_items,
        load_state,
        mark_submitted,
        save_state,
        touch_run,
    )

    items = load_magnets_from_result(
        result_path,
        today_only=today_only,
        region_filter=region_filter,
    )
    state_path = state_file or default_state_path(result_path.parent)
    state = load_state(state_path) if new_only else None
    if new_only and state is not None:
        before = len(items)
        items = filter_new_items(items, state)
        print(f"[info] new-only: {len(items)}/{before} magnet(s) since last run")
    if not items:
        print("[info] no magnets to submit")
        if new_only and state is not None:
            touch_run(state)
            save_state(state_path, state)
        return 0, 0
    print(f"[info] submitting {len(items)} cloud download task(s)...")
    ok, total, succeeded = submit_magnets(items, folder=folder, access_token=access_token)
    if new_only and state is not None:
        if succeeded:
            mark_submitted(state, succeeded)
        touch_run(state)
        save_state(state_path, state)
    return ok, total


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit magnets to PikPak cloud download")
    parser.add_argument(
        "--folder",
        default=None,
        help=f"Target folder name (default: saved or {DEFAULT_FOLDER})",
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
        help="Skip magnets already submitted in download_state.json",
    )
    parser.add_argument(
        "--state-file",
        default=None,
        help="Path to download state JSON (default: beside result file)",
    )
    args = parser.parse_args()

    result_path = Path(os.environ.get("RESULT_JSON", "last_result.json"))
    if not result_path.exists():
        print(f"[err] result file not found: {result_path}", file=sys.stderr)
        return 1

    try:
        from pikpak_auth import resolve_folder

        state_file = Path(args.state_file) if args.state_file else None
        ok, total = submit_from_result(
            result_path,
            folder=resolve_folder(args.folder, DEFAULT_FOLDER),
            today_only=not args.all,
            region_filter=not args.all_regions,
            new_only=args.new_only,
            state_file=state_file,
        )
    except RuntimeError as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 1

    print(f"\n[done] {ok}/{total} submitted")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
