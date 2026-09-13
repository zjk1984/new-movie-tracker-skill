# -*- coding: utf-8 -*-
"""
JavDB mobile App API client (ported from zjk1984/javdb-cli).

Uses jdsignature header auth against /api/v1..v4 endpoints.
Requires curl_cffi for TLS fingerprinting (plain urllib/requests often get HTTP 400).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_AUTH_FILE = SKILL_DIR / "javdb_auth.json"

try:
    from curl_cffi import requests as http
except ImportError as exc:
    raise ImportError(
        "javdb_client requires curl_cffi. Install with: pip install curl_cffi"
    ) from exc

# From JavDB.apk 1.9.28 (javdb-cli internal/javdb/protocol/signature/sign.go)
SIGN_PREFIX = (
    "71cf27bb3c0bcdf207b64abecddc970098c7421ee7203b9cdae54478478a199e7d5a6e1a57691123c1a931c057842fb73ba3b3c83bcd69c17ccf174081e3d8aa"
)
SIGN_SUFFIX = "lpw6vgqzsp"

APP_VERSION = "1.9.28"
APP_VERSION_NUMBER = "10928"
USER_AGENT = "Dart/3.4 (dart:io)"
HOST_MIRROR = "https://jdforrepam.com"
HOST_MAIN = "https://javdb.com"

AV_NUMBER_RE = re.compile(
    r"\b(?:FC2-PPV-\d+|FC2-\d+|HEYZO-\d+|[A-Z]{2,10}-\d{2,5})\b",
    re.IGNORECASE,
)


def sign(ts: int | None = None) -> str:
    if ts is None or ts <= 0:
        ts = int(time.time())
    digest = hashlib.md5(f"{ts}{SIGN_PREFIX}".encode()).hexdigest()
    return f"{ts}.{SIGN_SUFFIX}.{digest}"


def extract_av_number(text: str) -> str | None:
    m = AV_NUMBER_RE.search(text or "")
    return m.group(0).upper() if m else None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.lower() in ("true", "1")
    return False


def _any_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        n = 0
        for ch in value:
            if not ch.isdigit():
                break
            n = n * 10 + int(ch)
        return n
    return 0


def _any_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def magnet_uri(row: dict[str, Any]) -> str:
    h = _any_str(row.get("hash"))
    if not h:
        return ""
    return f"magnet:?xt=urn:btih:{h}"


def magnet_better(a: dict[str, Any], b: dict[str, Any]) -> bool:
    ac, bc = int(_truthy(a.get("cnsub"))), int(_truthy(b.get("cnsub")))
    if ac != bc:
        return ac > bc
    ah, bh = int(_truthy(a.get("hd"))), int(_truthy(b.get("hd")))
    if ah != bh:
        return ah > bh
    asz, bsz = _any_int(a.get("size")), _any_int(b.get("size"))
    if asz != bsz:
        return asz > bsz
    return _any_int(a.get("files_count")) > _any_int(b.get("files_count"))


def filter_magnets(
    magnets: list[dict[str, Any]],
    *,
    cnsub: bool = False,
    hd: bool = False,
    min_size: int = 0,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in magnets:
        if cnsub and not _truthy(row.get("cnsub")):
            continue
        if hd and not _truthy(row.get("hd")):
            continue
        if min_size > 0 and _any_int(row.get("size")) < min_size:
            continue
        out.append(row)
    return out


def pick_best_magnet(magnets: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not magnets:
        return None
    best = magnets[0]
    for row in magnets[1:]:
        if magnet_better(row, best):
            best = row
    return best


def resolve_number(movies: list[dict[str, Any]], number: str) -> str:
    want = number.strip().upper()
    if not want:
        raise ValueError("empty number")
    for movie in movies:
        if _any_str(movie.get("number")).upper() == want:
            movie_id = _any_str(movie.get("id"))
            if movie_id:
                return movie_id
            raise ValueError(f"match for {number} has no id")
    if movies:
        movie_id = _any_str(movies[0].get("id"))
        if movie_id:
            return movie_id
    raise LookupError(f"找不到番号: {number}")


def auth_file_path() -> Path:
    return Path(os.environ.get("JAVDB_AUTH_FILE", DEFAULT_AUTH_FILE))


def load_auth_store() -> dict[str, Any]:
    path = auth_file_path()
    if not path.exists():
        return {"default_username": "", "accounts": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"default_username": "", "accounts": []}
    if not isinstance(data, dict):
        return {"default_username": "", "accounts": []}
    data.setdefault("default_username", "")
    data.setdefault("accounts", [])
    return data


def save_auth_store(store: dict[str, Any]) -> None:
    path = auth_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_saved_token(username: str | None = None) -> str:
    store = load_auth_store()
    accounts = store.get("accounts") or []
    if not accounts:
        return ""
    want = username or store.get("default_username") or ""
    if want:
        for account in accounts:
            if isinstance(account, dict) and account.get("username") == want:
                return _any_str(account.get("token"))
    first = accounts[0]
    if isinstance(first, dict):
        return _any_str(first.get("token"))
    return ""


def upsert_auth_account(
    *,
    username: str,
    token: str,
    user_id: int | None = None,
    password: str | None = None,
    set_default: bool = True,
) -> None:
    store = load_auth_store()
    accounts = [a for a in store.get("accounts") or [] if isinstance(a, dict)]
    updated = False
    for account in accounts:
        if account.get("username") == username:
            account["token"] = token
            account["updated"] = datetime.now().isoformat(timespec="seconds")
            if user_id is not None:
                account["user_id"] = user_id
            if password is not None:
                account["password"] = password
            updated = True
            break
    if not updated:
        entry: dict[str, Any] = {
            "username": username,
            "token": token,
            "updated": datetime.now().isoformat(timespec="seconds"),
        }
        if user_id is not None:
            entry["user_id"] = user_id
        if password is not None:
            entry["password"] = password
        accounts.append(entry)
    store["accounts"] = accounts
    if set_default:
        store["default_username"] = username
    save_auth_store(store)


def remove_auth_account(username: str | None = None) -> bool:
    store = load_auth_store()
    accounts = [a for a in store.get("accounts") or [] if isinstance(a, dict)]
    if not accounts:
        return False
    target = username or store.get("default_username") or accounts[0].get("username")
    new_accounts = [a for a in accounts if a.get("username") != target]
    if len(new_accounts) == len(accounts):
        return False
    store["accounts"] = new_accounts
    if store.get("default_username") == target:
        store["default_username"] = _any_str(new_accounts[0].get("username")) if new_accounts else ""
    save_auth_store(store)
    return True


def resolve_number_exact(movies: list[dict[str, Any]], number: str) -> str:
    want = number.strip().upper()
    if not want:
        raise ValueError("empty number")
    selected = ""
    for movie in movies:
        if _any_str(movie.get("number")).upper() != want:
            continue
        movie_id = _any_str(movie.get("id"))
        if not movie_id:
            raise ValueError(f"exact match for {number} has no id")
        if selected:
            raise LookupError(f"番号 {number} 有多个精确匹配")
        selected = movie_id
    if not selected:
        raise LookupError(f"找不到番号: {number}")
    return selected


class JavDBClient:
    def __init__(
        self,
        *,
        host: str | None = None,
        token: str | None = None,
        device_uuid: str | None = None,
        lang: str = "en",
        timeout: float = 20.0,
        retries: int = 2,
        use_saved_token: bool = True,
    ) -> None:
        self.host = (host or os.environ.get("JAVDB_HOST") or HOST_MIRROR).rstrip("/")
        self.token = token or os.environ.get("JAVDB_TOKEN") or ""
        if not self.token and use_saved_token:
            self.token = load_saved_token()
        self.device_uuid = device_uuid or os.environ.get("JAVDB_DEVICE_UUID") or str(uuid.uuid4())
        self.lang = lang
        self.timeout = timeout
        self.retries = max(0, retries)
        self.public = {
            "app_channel": "official",
            "app_version": APP_VERSION,
            "app_version_number": APP_VERSION_NUMBER,
            "platform": "android",
            "system_version": "13",
            "device_model": "Pixel 6",
            "device_name": "Pixel",
            "device_uuid": self.device_uuid,
        }

    def _headers(self) -> dict[str, str]:
        headers = {
            "jdsignature": sign(),
            "accept-language": self.lang,
            "connection": "keep-alive",
            "user-agent": USER_AGENT,
        }
        if self.token:
            headers["authorization"] = f"Bearer {self.token}"
        return headers

    def _merge_params(self, extra: dict[str, str] | None) -> dict[str, str]:
        params = dict(self.public)
        if extra:
            for key, value in extra.items():
                if value:
                    params[key] = value
        return params

    def _request(self, method: str, path: str, params: dict[str, str] | None = None) -> Any:
        url = f"{self.host}{path}"
        merged = self._merge_params(params)
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                method_upper = method.upper()
                if method_upper == "GET":
                    resp = http.get(
                        url,
                        params=merged,
                        headers=self._headers(),
                        impersonate="chrome120",
                        timeout=self.timeout,
                    )
                elif method_upper == "POST":
                    resp = http.post(
                        url,
                        data=merged,
                        headers=self._headers(),
                        impersonate="chrome120",
                        timeout=self.timeout,
                    )
                else:
                    raise ValueError(f"unsupported method: {method}")
                if resp.status_code >= 400:
                    raise RuntimeError(f"http {resp.status_code}: {resp.text[:200]}")
                payload = resp.json()
                if not _truthy(payload.get("success")):
                    action = _any_str(payload.get("action"))
                    message = _any_str(payload.get("message"))
                    raise RuntimeError(f"{action}: {message}".strip(": "))
                data = payload.get("data")
                if data is None or data == "null":
                    return {}
                return data
            except Exception as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                break
        raise RuntimeError(str(last_error) if last_error else "request failed")

    def login(self, username: str, password: str) -> str:
        data = self._request(
            "POST",
            "/api/v1/sessions",
            {"username": username.strip(), "password": password},
        )
        token = _any_str(data.get("token") or data.get("access_token"))
        if not token:
            raise RuntimeError("login response had no token")
        self.token = token
        return token

    def user_profile(self) -> dict[str, Any]:
        data = self._request("GET", "/api/v1/users")
        if isinstance(data, dict) and isinstance(data.get("user"), dict):
            return data["user"]
        return data if isinstance(data, dict) else {}

    def check_auth(self) -> dict[str, Any]:
        profile = self.user_profile()
        if not profile:
            raise RuntimeError("not logged in or token invalid")
        return profile

    def search(self, query: str, *, page: int = 1, limit: int = 0) -> list[dict[str, Any]]:
        params = {"q": query, "page": str(page)}
        if limit > 0:
            params["limit"] = str(limit)
        data = self._request("GET", "/api/v2/search", params)
        movies = data.get("movies") if isinstance(data, dict) else None
        return movies if isinstance(movies, list) else []

    def resolve_movie_id(self, number: str, *, exact: bool = False) -> str:
        movies = self.search(number, page=1, limit=100 if exact else 0)
        if exact:
            return resolve_number_exact(movies, number)
        return resolve_number(movies, number)

    def movie_detail(self, movie_id: str) -> dict[str, Any]:
        data = self._request("GET", f"/api/v4/movies/{movie_id}")
        if isinstance(data, dict) and isinstance(data.get("movie"), dict):
            return data["movie"]
        return data if isinstance(data, dict) else {}

    def movie_magnets(self, movie_id: str) -> list[dict[str, Any]]:
        data = self._request("GET", f"/api/v1/movies/{movie_id}/magnets")
        magnets = data.get("magnets") if isinstance(data, dict) else None
        return magnets if isinstance(magnets, list) else []

    def lookup(
        self,
        number: str,
        *,
        exact: bool = True,
        fetch_magnets: bool = False,
        cnsub: bool = False,
        hd: bool = False,
        best_only: bool = False,
    ) -> dict[str, Any]:
        movie_id = self.resolve_movie_id(number, exact=exact)
        detail = self.movie_detail(movie_id)
        resolved_number = _any_str(detail.get("number") or number).upper()
        content_type = classify_javdb_content(detail, resolved_number)
        result: dict[str, Any] = {
            "number": resolved_number,
            "javdb_id": movie_id,
            "title": _any_str(detail.get("title")),
            "release_date": _any_str(detail.get("release_date")),
            "duration": detail.get("duration"),
            "has_cnsub": detail.get("has_cnsub"),
            "content_type": content_type,
            "content_type_label": content_type_label(content_type),
            "query_status": "ok",
        }
        if fetch_magnets:
            all_rows = self.movie_magnets(movie_id)
            result["magnet_total"] = len(all_rows)
            magnets = filter_magnets(all_rows, cnsub=cnsub, hd=hd)
            result["magnet_filtered"] = len(magnets)
            if best_only:
                best = pick_best_magnet(magnets)
                magnets = [best] if best else []
            uri_list = [magnet_uri(m) for m in magnets if magnet_uri(m)]
            result["magnets"] = uri_list
            result["magnet_rows"] = magnets
            result["magnet_status"] = "available" if uri_list else "empty"
            result["best_magnet"] = uri_list[0] if uri_list else ""
        else:
            result["magnet_status"] = "not_requested"
            result["magnet_total"] = 0
            result["magnet_filtered"] = 0
            result["best_magnet"] = ""
        result["summary"] = format_lookup_summary(result)
        return result


def classify_javdb_content(detail: dict[str, Any], number: str) -> str:
    from content_filter import STUDIO_NUM_RE, classify_region

    title = _any_str(detail.get("title"))
    region = classify_region({"title": title, "av_number": number})
    if region in ("jav_censored", "uncensored"):
        return region
    if STUDIO_NUM_RE.match(number.upper()):
        return "jav_censored"
    return "other"


def content_type_label(content_type: str) -> str:
    return {"jav_censored": "有码", "uncensored": "无码"}.get(content_type, "其他")


def format_lookup_summary(info: dict[str, Any], *, error: str | None = None) -> str:
    if error:
        return f"JavDB 查询失败: {error}"
    number = info.get("number", "?")
    label = info.get("content_type_label") or content_type_label(info.get("content_type", ""))
    parts = [f"JavDB {number} [{label}]", f"发行 {info.get('release_date') or '-'}"]
    if info.get("has_cnsub"):
        parts.append("库内标注含中字")
    status = info.get("magnet_status")
    if status == "available":
        total = info.get("magnet_total", 0)
        filtered = info.get("magnet_filtered", len(info.get("magnets") or []))
        parts.append(f"磁力 {filtered}/{total} 条可用")
    elif status == "empty":
        parts.append(f"JavDB 暂无磁力 (库内共 {info.get('magnet_total', 0)} 条)")
    elif status == "not_requested":
        parts.append("未请求磁力")
    return " | ".join(parts)


def build_query_report(info: dict[str, Any]) -> dict[str, Any]:
    return {
        "query_status": info.get("query_status", "ok"),
        "number": info.get("number"),
        "content_type": info.get("content_type"),
        "content_type_label": info.get("content_type_label"),
        "release_date": info.get("release_date"),
        "title": info.get("title"),
        "has_cnsub": info.get("has_cnsub"),
        "magnet_status": info.get("magnet_status"),
        "magnet_total": info.get("magnet_total", 0),
        "magnet_filtered": info.get("magnet_filtered", 0),
        "best_magnet": info.get("best_magnet") or ((info.get("magnets") or [""])[0]),
        "summary": info.get("summary") or format_lookup_summary(info),
    }


def build_error_report(number: str, error: str) -> dict[str, Any]:
    return {
        "query_status": "error",
        "number": number,
        "content_type": "",
        "content_type_label": "",
        "release_date": "",
        "title": "",
        "has_cnsub": None,
        "magnet_status": "error",
        "magnet_total": 0,
        "magnet_filtered": 0,
        "best_magnet": "",
        "summary": format_lookup_summary({}, error=error),
        "error": error,
    }


def attach_javdb_query(item: dict[str, Any], client: JavDBClient) -> None:
    """Query JavDB by number and attach javdb_query report to item."""
    number = item.get("av_number") or extract_av_number(item.get("title", ""))
    if not number:
        return
    item["av_number"] = number
    try:
        info = client.lookup(number, fetch_magnets=True, best_only=True)
        item["javdb_query"] = build_query_report(info)
        item["javdb"] = {
            "id": info.get("javdb_id"),
            "number": info.get("number"),
            "title": info.get("title"),
            "release_date": info.get("release_date"),
            "content_type": info.get("content_type"),
            "content_type_label": info.get("content_type_label"),
        }
        if info.get("release_date") and not item.get("release_date"):
            item["release_date"] = info["release_date"]
    except Exception as exc:
        item["javdb_query"] = build_error_report(number, str(exc))
        item["javdb_error"] = str(exc)
