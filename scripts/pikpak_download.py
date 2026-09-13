#!/usr/bin/env python3
"""Submit magnet / feature-code links to PikPak cloud download via API."""
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


def sha_api_headers(access_token: str, device_id: str, captcha_token: str) -> dict:
    headers = api_headers(access_token, device_id, captcha_token)
    headers.update({
        "Product_flavor_name": "cha",
        "X-Client-Version-Code": "10083",
        "X-Peer-Id": device_id,
        "X-User-Region": "1",
        "X-Alt-Capability": "3",
        "Country": "CN",
    })
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


def offline_download_url(
    session: requests.Session,
    access_token: str,
    device_id: str,
    user_id: str,
    name: str,
    url: str,
    parent_id: str | None = None,
) -> dict:
    body = {
        "kind": "drive#file",
        "name": name,
        "upload_type": "UPLOAD_TYPE_URL",
        "url": {"url": url},
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


def offline_download_sha(
    session: requests.Session,
    access_token: str,
    device_id: str,
    user_id: str,
    name: str,
    size: str,
    file_hash: str,
    parent_id: str | None = None,
) -> dict:
    """Instant-add by PikPak GCID feature code (秒传)."""
    body = {
        "body": {"duration": "", "width": "", "height": ""},
        "kind": "drive#file",
        "name": name,
        "size": str(size),
        "hash": file_hash.upper(),
        "upload_type": "UPLOAD_TYPE_RESUMABLE",
        "objProvider": {"provider": "UPLOAD_TYPE_UNKNOWN"},
    }
    if parent_id:
        body["parent_id"] = parent_id
    captcha_token = get_captcha_token(session, device_id, user_id, "POST:/drive/v1/files")
    resp = session.post(
        f"{DRIVE_HOST}/drive/v1/files",
        headers=sha_api_headers(access_token, device_id, captcha_token),
        json=body,
        timeout=30,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"{name}: HTTP {resp.status_code} {resp.text[:500]}")
    data = resp.json()
    file_info = data.get("file") or {}
    phase = file_info.get("phase") or ""
    if phase != "PHASE_TYPE_COMPLETE":
        raise RuntimeError(
            f"{name}: feature code not in PikPak cache (phase={phase or 'unknown'})"
        )
    return data


def pick_item_magnet(item: dict) -> str | None:
    selected = (item.get("selected_magnet") or "").strip()
    if selected:
        return selected
    magnets = item.get("magnets") or []
    return magnets[0] if magnets else None


def item_download_name(item: dict, fallback: str = "download") -> str:
    for key in ("av_number", "name"):
        value = item.get(key)
        if value:
            return str(value)
    title = item.get("title", fallback)
    return title.split()[0] if title else fallback


def pick_item_download(item: dict) -> dict | None:
    from pikpak_links import parse_download_link, parse_pikpak_sha

    if item.get("selected_download"):
        parsed = parse_download_link(item["selected_download"])
        if parsed:
            parsed.setdefault("name", item_download_name(item, parsed.get("name", "download")))
            parsed.setdefault("source", item.get("download_source") or item.get("magnet_source", ""))
            return parsed

    if item.get("selected_pikpak_sha"):
        parsed = parse_pikpak_sha(item["selected_pikpak_sha"])
        if parsed:
            parsed["source"] = item.get("download_source") or "forum_pikpak_sha"
            return parsed

    if item.get("selected_ed2k"):
        parsed = parse_download_link(item["selected_ed2k"])
        if parsed:
            parsed["name"] = item_download_name(item, parsed.get("name", "download"))
            parsed["source"] = item.get("download_source") or "forum_ed2k"
            return parsed

    for sha in item.get("pikpak_sha") or []:
        parsed = parse_pikpak_sha(sha)
        if parsed:
            parsed["source"] = "forum_pikpak_sha"
            return parsed

    magnet = pick_item_magnet(item)
    if magnet:
        return {
            "type": "url",
            "url": magnet,
            "uri": magnet,
            "name": item_download_name(item),
            "source": item.get("magnet_source", ""),
        }

    for ed2k in item.get("ed2k") or []:
        parsed = parse_download_link(ed2k)
        if parsed:
            parsed["name"] = item_download_name(item, parsed.get("name", "download"))
            parsed["source"] = "forum_ed2k"
            return parsed

    return None


def load_downloads_from_result(
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
        download = pick_item_download(item)
        if not download:
            continue
        title = item.get("title", "download")
        entry = {
            "name": download.get("name") or item_download_name(item),
            "title": title,
            "type": download["type"],
            "source": download.get("source", ""),
            "href": item.get("href", ""),
            "av_number": item.get("av_number", ""),
            "uri": download.get("uri") or download.get("url") or "",
        }
        if download["type"] == "sha":
            entry.update({
                "size": download["size"],
                "hash": download["hash"],
                "pikpak_sha": download["uri"],
            })
        else:
            entry["url"] = download["url"]
            entry["magnet"] = download["url"]
        items.append(entry)
    return items


def load_today_magnets(result_path: Path) -> list[dict]:
    return load_downloads_from_result(result_path, today_only=True)


def submit_one_download(
    session: requests.Session,
    token: str,
    device_id: str,
    user_id: str,
    item: dict,
    *,
    parent_id: str | None,
) -> dict:
    if item.get("type") == "sha":
        return offline_download_sha(
            session,
            token,
            device_id,
            user_id,
            item["name"],
            item["size"],
            item["hash"],
            parent_id=parent_id,
        )
    url = item.get("url") or item.get("magnet") or ""
    return offline_download_url(
        session,
        token,
        device_id,
        user_id,
        item["name"],
        url,
        parent_id=parent_id,
    )


def submit_downloads(
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
        kind = "sha" if item.get("type") == "sha" else "url"
        try:
            result = submit_one_download(
                session, token, device_id, user_id, item, parent_id=parent_id,
            )
            task = result.get("task") or {}
            file_info = result.get("file") or {}
            task_id = task.get("id") or file_info.get("id") or "unknown"
            phase = task.get("phase") or file_info.get("phase") or "submitted"
            source = item.get("source")
            suffix = f" [{source}]" if source else ""
            label = f"{item['name']} ({kind})"
            print(f"[ok] {label}{suffix} -> task={task_id} phase={phase}")
            print(f"     {item['title'][:80]}")
            ok += 1
            succeeded.append(item)
        except Exception as exc:
            print(f"[err] {item['name']} ({kind}): {exc}", file=sys.stderr)
    return ok, len(items), succeeded


# Backward-compatible alias
submit_magnets = submit_downloads


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

    items = load_downloads_from_result(
        result_path,
        today_only=today_only,
        region_filter=region_filter,
    )
    state_path = state_file or default_state_path(result_path.parent)
    state = load_state(state_path) if new_only else None
    if new_only and state is not None:
        before = len(items)
        items = filter_new_items(items, state)
        print(f"[info] new-only: {len(items)}/{before} download(s) since last run")
    if not items:
        print("[info] no downloads to submit")
        if new_only and state is not None:
            touch_run(state)
            save_state(state_path, state)
        return 0, 0
    print(f"[info] submitting {len(items)} cloud download task(s)...")
    ok, total, succeeded = submit_downloads(items, folder=folder, access_token=access_token)
    if new_only and state is not None:
        if succeeded:
            mark_submitted(state, succeeded)
        touch_run(state)
        save_state(state_path, state)
    return ok, total


def load_sha_args(values: list[str], sha_file: str | None) -> list[dict]:
    from pikpak_links import parse_pikpak_sha

    lines = list(values)
    if sha_file:
        lines.extend(Path(sha_file).read_text(encoding="utf-8").splitlines())
    items = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parsed = parse_pikpak_sha(line)
        if not parsed:
            raise ValueError(f"invalid PikPak feature code: {line}")
        items.append({
            "type": "sha",
            "name": parsed["name"],
            "size": parsed["size"],
            "hash": parsed["hash"],
            "uri": parsed["uri"],
            "pikpak_sha": parsed["uri"],
            "title": parsed["name"],
            "source": "cli_sha",
        })
    return items


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Submit magnets / PikPak feature codes to cloud download",
    )
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
        help="Skip downloads already submitted in download_state.json",
    )
    parser.add_argument(
        "--state-file",
        default=None,
        help="Path to download state JSON (default: beside result file)",
    )
    parser.add_argument(
        "--sha",
        action="append",
        default=[],
        help="PikPak feature code: PikPak://filename|size|gcid_hash",
    )
    parser.add_argument(
        "--sha-file",
        default=None,
        help="Text file with one PikPak feature code per line",
    )
    args = parser.parse_args()

    from pikpak_auth import resolve_folder

    folder = resolve_folder(args.folder, DEFAULT_FOLDER)

    if args.sha or args.sha_file:
        try:
            items = load_sha_args(args.sha, args.sha_file)
            if not items:
                print("[err] no feature codes provided", file=sys.stderr)
                return 1
            ok, total, _ = submit_downloads(items, folder=folder)
        except (RuntimeError, ValueError) as exc:
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
            folder=folder,
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
