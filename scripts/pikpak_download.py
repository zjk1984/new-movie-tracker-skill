#!/usr/bin/env python3
"""Submit magnet links to PikPak cloud download via API."""
import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path

import requests

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


def offline_download(
    session: requests.Session,
    access_token: str,
    device_id: str,
    user_id: str,
    name: str,
    magnet: str,
) -> dict:
    body = {
        "kind": "drive#file",
        "name": name,
        "upload_type": "UPLOAD_TYPE_URL",
        "url": {"url": magnet},
    }
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


def load_today_magnets(result_path: Path) -> list[dict]:
    data = json.loads(result_path.read_text(encoding="utf-8"))
    today = data.get("today") or data.get("scan_time", "")[:10]
    items = []
    for item in data.get("matched", []):
        if item.get("date") != today:
            continue
        magnets = item.get("magnets") or []
        if not magnets:
            continue
        title = item.get("title", "download")
        code = title.split()[0] if title else "download"
        items.append({"name": code, "title": title, "magnet": magnets[0]})
    return items


def main() -> int:
    access_token = os.environ.get("PIKPAK_TOKEN", "").strip()
    if not access_token:
        print("[err] set PIKPAK_TOKEN environment variable", file=sys.stderr)
        return 1

    payload = decode_jwt_payload(access_token)
    user_id = payload.get("sub", "")
    device_id = hashlib.md5(user_id.encode()).hexdigest()

    result_path = Path(os.environ.get("RESULT_JSON", "/workspace/last_result.json"))
    if not result_path.exists():
        print(f"[err] result file not found: {result_path}", file=sys.stderr)
        return 1

    items = load_today_magnets(result_path)
    if not items:
        print("[info] no magnets for today in result file")
        return 0

    session = requests.Session()
    print(f"[info] submitting {len(items)} cloud download task(s)...")

    ok = 0
    for item in items:
        try:
            result = offline_download(
                session, access_token, device_id, user_id, item["name"], item["magnet"]
            )
            task = result.get("task") or {}
            file_info = result.get("file") or {}
            task_id = task.get("id") or file_info.get("id") or "unknown"
            phase = task.get("phase") or file_info.get("phase") or "submitted"
            print(f"[ok] {item['name']} -> task={task_id} phase={phase}")
            print(f"     {item['title'][:80]}")
            ok += 1
        except Exception as e:
            print(f"[err] {item['name']}: {e}", file=sys.stderr)

    print(f"\n[done] {ok}/{len(items)} submitted")
    return 0 if ok == len(items) else 1


if __name__ == "__main__":
    sys.exit(main())
