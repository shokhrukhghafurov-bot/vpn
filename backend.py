from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit, unquote, quote
import base64
import hashlib
import html
import json
import secrets
from uuid import uuid4
import time
import threading
import socket


import jwt
import requests
import psycopg
from psycopg.rows import dict_row
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBasic, HTTPBasicCredentials, HTTPBearer
from pydantic import BaseModel, Field

from config import settings
from db_store import (
    activate_payment_and_extend_subscription,
    admin_create_or_update_user,
    bootstrap,
    create_location,
    create_payment_record,
    delete_device,
    delete_location,
    export_payments_csv,
    _compose_vpn_payload_for_location,
    _normalize_vpn_payload_keys,
    _config_is_complete,
    _pick_virtual_location,
    get_active_plans,
    get_payment_by_internal_or_external,
    get_payment_for_user,
    get_plan_by_code,
    get_vpn_config_for_user,
    get_user_by_id,
    get_user_by_subscription_token,
    get_user_by_active_auth_code,
    get_user_by_telegram_id,
    get_user_snapshot_by_telegram,
    get_user_subscription_view,
    get_subscription_device_gate_by_token,
    ensure_user_subscription_token,
    issue_auth_code,
    consume_auth_code,
    list_admin_users,
    list_bot_errors,
    list_broadcast_targets,
    list_locations,
    list_payments,
    patch_location,
    record_bot_error,
    refresh_subscription_statuses,
    register_device,
    touch_subscription_device_by_token,
    reset_user_devices_by_telegram,
    set_user_device_limit_override_by_telegram,
    set_user_language,
    set_user_status_by_telegram,
    settings_snapshot,
    save_runtime_settings_payload,
    sync_plans_from_env,
    upsert_telegram_user,
    update_payment,
    extend_user_subscription_by_telegram,
    enqueue_notification,
    _get_user_subscription_view_with_conn,
)


app = FastAPI(title=f"{settings.APP_NAME} VPN API")
security = HTTPBearer(auto_error=False)
basic_security = HTTPBasic()


class TelegramAuthIn(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    language: str = "ru"


class CodeAuthIn(BaseModel):
    code: str
    telegram_id: Optional[int] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    language: str = "ru"


class IssueCodeIn(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    language: str = "ru"


class RefreshIn(BaseModel):
    refresh_token: Optional[str] = None


class LanguageIn(BaseModel):
    language: str = "ru"


class DeviceRegisterIn(BaseModel):
    platform: str
    device_name: str
    device_fingerprint: str


class PaymentCreateIn(BaseModel):
    plan_code: str
    method: str = "telegram"


class AdminUserUpsertIn(BaseModel):
    telegram_id: int
    plan_code: str
    expires_at: Optional[datetime] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    language: str = "ru"
    device_limit_override: Optional[int] = Field(default=None, ge=1)


class AdminUserPatchIn(BaseModel):
    device_limit_override: Optional[int] = None


class ExtendIn(BaseModel):
    days_added: Optional[int] = Field(default=None, gt=0)
    days: Optional[int] = Field(default=None, gt=0)
    reason: str = "manual extension"

    def normalized_days(self) -> int:
        return int(self.days_added or self.days or 30)


class LocationIn(BaseModel):
    code: str
    name_ru: str
    name_en: str
    country_code: Optional[str] = None
    is_active: bool = True
    is_recommended: bool = False
    is_reserve: bool = False
    status: str = "online"
    sort_order: int = 100
    download_mbps: Optional[float] = None
    upload_mbps: Optional[float] = None
    ping_ms: Optional[int] = None
    speed_checked_at: Optional[str] = None
    vpn_payload: Dict[str, Any] = Field(default_factory=dict)


class LocationPatchIn(BaseModel):
    name_ru: Optional[str] = None
    name_en: Optional[str] = None
    country_code: Optional[str] = None
    is_active: Optional[bool] = None
    is_recommended: Optional[bool] = None
    is_reserve: Optional[bool] = None
    status: Optional[str] = None
    sort_order: Optional[int] = None
    download_mbps: Optional[float] = None
    upload_mbps: Optional[float] = None
    ping_ms: Optional[int] = None
    speed_checked_at: Optional[str] = None
    vpn_payload: Optional[Dict[str, Any]] = None


class BroadcastIn(BaseModel):
    text: str = ""
    statuses: List[str] = Field(default_factory=lambda: ["active"])


class TestSendIn(BaseModel):
    telegram_id: int
    text: str


class VpnClientEventIn(BaseModel):
    platform: str
    stage: str = "runtime"
    status: Optional[str] = None
    location_code: Optional[str] = None
    error_message: Optional[str] = None
    details: Optional[str] = None


class AdminPlanSettingsIn(BaseModel):
    slot: str
    code: str
    name_ru: str
    name_en: Optional[str] = None
    price_rub: int = Field(default=0, ge=0)
    duration_days: int = Field(default=1, ge=1)
    device_limit: int = Field(default=1, ge=1)
    is_active: bool = True


class AdminVpnSettingsIn(BaseModel):
    app_name: str
    app_env: str = "production"
    languages: List[str] = Field(default_factory=lambda: ["ru", "en"])
    bot_name: str
    bot_username: str
    support_telegram_url: str
    payments_enabled: bool = False
    maintenance_mode: bool = False
    new_activations_enabled: bool = True
    max_devices_per_account: int = Field(default=1, ge=1)
    device_limit: Optional[int] = Field(default=None, ge=1)
    plans: List[AdminPlanSettingsIn] = Field(default_factory=list)


RU_LTE_LOCATION_CODES: Tuple[str, ...] = ("ru-lte", "ru-lte-reserve-1", "ru-lte-reserve-2", "ru-lte-reserve-3")
BLACK_LOCATION_CODES: Tuple[str, ...] = ("intl-fast", "intl-fast-reserve-1", "intl-fast-reserve-2", "intl-fast-reserve-3")


def _read_text_from_source(source: str) -> str:
    raw = str(source or "").strip()
    if not raw:
        return ""
    if raw.startswith(("http://", "https://")):
        response = requests.get(raw, timeout=20, headers={"Accept": "text/plain, text/html;q=0.9, */*;q=0.8"})
        response.raise_for_status()
        return response.text
    with open(raw, "r", encoding="utf-8") as fh:
        return fh.read()


def _decode_vless_name(fragment: str) -> str:
    return unquote(fragment or "").strip()


def _parse_vless_subscription_line(line: str) -> Optional[Dict[str, Any]]:
    raw = str(line or "").strip()
    if not raw.startswith("vless://"):
        return None
    base, _, fragment = raw.partition("#")
    parsed = urlsplit(base)
    if parsed.scheme.lower() != "vless":
        return None
    uuid = unquote(parsed.username or "").strip()
    server = (parsed.hostname or "").strip()
    try:
        port = int(parsed.port or 0)
    except (TypeError, ValueError):
        port = 0
    if not uuid or not server or port <= 0:
        return None
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    transport = (query.get("type") or query.get("transport") or query.get("network") or "tcp").strip() or "tcp"
    payload: Dict[str, Any] = {
        "engine": "nekobox",
        "protocol": "vless",
        "server": server,
        "port": port,
        "uuid": uuid,
        "transport": transport,
        "network": transport,
        "security": (query.get("security") or "reality").strip() or "reality",
        "flow": (query.get("flow") or "").strip(),
        "sni": (query.get("sni") or query.get("serverName") or query.get("host") or "").strip(),
        "server_name": (query.get("sni") or query.get("serverName") or query.get("host") or "").strip(),
        "public_key": (query.get("pbk") or query.get("public_key") or query.get("publicKey") or "").strip(),
        "short_id": (query.get("sid") or query.get("short_id") or query.get("shortId") or "").strip(),
        "fingerprint": (query.get("fp") or query.get("fingerprint") or "chrome").strip() or "chrome",
        "service_name": (query.get("serviceName") or query.get("service_name") or "").strip(),
        "path": (query.get("path") or query.get("spx") or "").strip(),
        "packet_encoding": (query.get("packetEncoding") or query.get("packet_encoding") or query.get("packet-encoding") or "xudp").strip() or "xudp",
        "remark": _decode_vless_name(fragment),
        "dns_servers": ["1.1.1.1", "8.8.8.8"],
        "connect_mode": "tun",
        "full_tunnel": True,
    }
    if query.get("mode"):
        payload["mode"] = query.get("mode")
    if query.get("host"):
        payload["host"] = query.get("host")
    if query.get("alpn"):
        payload["alpn"] = [item.strip() for item in str(query.get("alpn") or "").split(",") if item.strip()]
    return _normalize_vpn_payload_keys(payload)


def _transport_allowed(payload: Dict[str, Any], allowed_values: List[str]) -> bool:
    allowed = {item.strip().lower() for item in (allowed_values or []) if str(item or "").strip()}
    transport = str(payload.get("transport") or payload.get("network") or "tcp").strip().lower()
    return transport in allowed if allowed else True


def _probe_candidate_with_timeout(payload: Dict[str, Any], timeout_seconds: float) -> Dict[str, Any]:
    server = str(payload.get("server") or "").strip()
    port = int(payload.get("port") or 0)
    if not server or port <= 0:
        return {"ok": False, "latency_ms": None, "error": "missing_server_or_port"}

    started = time.perf_counter()
    try:
        addr_infos = socket.getaddrinfo(server, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        return {"ok": False, "latency_ms": None, "error": f"dns:{exc}"}

    timeout = max(1.0, float(timeout_seconds or 4))
    last_error = None
    for family, socktype, proto, _canonname, sockaddr in addr_infos[:4]:
        sock = None
        try:
            sock = socket.socket(family, socktype, proto)
            sock.settimeout(timeout)
            sock.connect(sockaddr)
            latency_ms = int((time.perf_counter() - started) * 1000)
            return {"ok": True, "latency_ms": latency_ms, "error": None}
        except OSError as exc:
            last_error = str(exc)
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
    return {"ok": False, "latency_ms": None, "error": last_error or "connect_failed"}


def _ru_lte_transport_bonus(payload: Dict[str, Any]) -> int:
    transport = str(payload.get("transport") or payload.get("network") or "tcp").strip().lower()
    if transport == "xhttp":
        return 60
    if transport == "grpc":
        return 50
    if transport in {"ws", "websocket"}:
        return 40
    if transport == "tcp":
        return -25
    return -50


def _ru_lte_source_priority(source: str) -> int:
    raw = str(source or "").strip().lower()
    if raw.endswith("/vless-reality-white-lists-rus-mobile.txt") or raw.endswith("vless-reality-white-lists-rus-mobile.txt"):
        return 40
    if raw.endswith("/vless-reality-white-lists-rus-mobile-2.txt") or raw.endswith("vless-reality-white-lists-rus-mobile-2.txt"):
        return 30
    if raw.endswith("/white-cidr-ru-checked.txt") or raw.endswith("white-cidr-ru-checked.txt"):
        return 20
    if raw.endswith("/white-cidr-ru-all.txt") or raw.endswith("white-cidr-ru-all.txt"):
        return 10
    if raw.endswith("/white-sni-ru-all.txt") or raw.endswith("white-sni-ru-all.txt"):
        return 0
    return 0


def _ru_lte_transport_allowed(payload: Dict[str, Any]) -> bool:
    allowed = {item.strip().lower() for item in (settings.RU_LTE_ALLOWED_TRANSPORTS or ["grpc", "tcp", "ws", "xhttp"]) if str(item or "").strip()}
    transport = str(payload.get("transport") or payload.get("network") or "tcp").strip().lower()
    return transport in allowed


def _ru_lte_probe_candidate(payload: Dict[str, Any]) -> Dict[str, Any]:
    server = str(payload.get("server") or "").strip()
    port = int(payload.get("port") or 0)
    if not server or port <= 0:
        return {"ok": False, "latency_ms": None, "error": "missing_server_or_port"}

    started = time.perf_counter()
    try:
        addr_infos = socket.getaddrinfo(server, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        return {"ok": False, "latency_ms": None, "error": f"dns:{exc}"}

    timeout = max(1.0, float(settings.RU_LTE_CONNECT_TIMEOUT_SEC or 4))
    last_error = None
    for family, socktype, proto, _canonname, sockaddr in addr_infos[:4]:
        sock = None
        try:
            sock = socket.socket(family, socktype, proto)
            sock.settimeout(timeout)
            sock.connect(sockaddr)
            latency_ms = int((time.perf_counter() - started) * 1000)
            return {"ok": True, "latency_ms": latency_ms, "error": None}
        except OSError as exc:
            last_error = str(exc)
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
    return {"ok": False, "latency_ms": None, "error": last_error or "connect_failed"}


def _ru_lte_payload_score(payload: Dict[str, Any]) -> int:
    score = 0
    score += _ru_lte_transport_bonus(payload)
    security = str(payload.get("security") or "").strip().lower()
    if security == "reality":
        score += 30
    elif security == "tls":
        score += 20
    if str(payload.get("flow") or "").strip().lower() == "xtls-rprx-vision":
        score += 15
    remark = str(payload.get("remark") or "").lower()
    if "cidr" in remark:
        score += 20
    if payload.get("server_name"):
        score += 5
    if payload.get("public_key") and payload.get("short_id"):
        score += 5
    latency = payload.get("_latency_ms")
    if isinstance(latency, int):
        if latency <= 150:
            score += 35
        elif latency <= 300:
            score += 20
        elif latency <= 600:
            score += 5
        else:
            score -= 20
    if payload.get("_probe_ok"):
        score += 50
    return score


def _patch_location_by_code(code: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for row in list_locations(active_only=False):
        if str(row.get("code") or "") == code:
            return patch_location(int(row.get("id")), updates)

    default_names = {
        "ru-lte": ("Россия LTE", "Russia LTE", False),
        "ru-lte-reserve-1": ("Россия LTE | Резерв 1", "Russia LTE | Reserve 1", True),
        "ru-lte-reserve-2": ("Россия LTE | Резерв 2", "Russia LTE | Reserve 2", True),
        "ru-lte-reserve-3": ("Россия LTE | Резерв 3", "Russia LTE | Reserve 3", True),
    }
    if code not in default_names:
        return None

    name_ru, name_en, is_reserve = default_names[code]
    base_payload = dict(updates.get("vpn_payload") or {})
    if base_payload:
        base_payload.setdefault("location_code", code)
        base_payload.setdefault("remark", name_en)

    payload = {
        "code": code,
        "name_ru": str(updates.get("name_ru") or name_ru),
        "name_en": str(updates.get("name_en") or name_en),
        "country_code": "RU",
        "is_active": bool(updates.get("is_active", True)),
        "is_recommended": bool(updates.get("is_recommended", code == "ru-lte")),
        "is_reserve": bool(updates.get("is_reserve", is_reserve)),
        "status": str(updates.get("status") or "offline"),
        "sort_order": int(updates.get("sort_order") or {"ru-lte": 30, "ru-lte-reserve-1": 31, "ru-lte-reserve-2": 32, "ru-lte-reserve-3": 33}.get(code, 100)),
        "vpn_payload": base_payload,
        "location_source": "catalog",
    }
    return create_location(payload)


def refresh_ru_lte_locations() -> Dict[str, Any]:
    sources = [item for item in (settings.RU_LTE_SOURCE_URLS or []) if str(item or "").strip()]
    candidates: List[Dict[str, Any]] = []
    seen: set[str] = set()
    source_stats: List[Dict[str, Any]] = []

    for source in sources:
        stat = {"source": source, "lines": 0, "accepted": 0, "error": None}
        try:
            content = _read_text_from_source(source)
            for line in content.splitlines():
                stat["lines"] += 1
                payload = _parse_vless_subscription_line(line)
                if not payload:
                    continue
                if str(payload.get("security") or "").strip().lower() != "reality":
                    continue
                normalized = _normalize_vpn_payload_keys(payload)
                if not _config_is_complete(normalized):
                    continue
                if not _ru_lte_transport_allowed(normalized):
                    continue
                key = "|".join([
                    str(normalized.get("server") or ""),
                    str(normalized.get("port") or ""),
                    str(normalized.get("uuid") or ""),
                    str(normalized.get("public_key") or ""),
                    str(normalized.get("short_id") or ""),
                    str(normalized.get("server_name") or normalized.get("sni") or ""),
                ])
                if key in seen:
                    continue
                seen.add(key)
                normalized["_source"] = source
                normalized["_source_priority"] = _ru_lte_source_priority(source)
                normalized["_score"] = _ru_lte_payload_score(normalized)
                candidates.append(normalized)
                stat["accepted"] += 1
        except Exception as exc:
            stat["error"] = str(exc)
        source_stats.append(stat)

    candidates.sort(key=lambda item: (int(item.get("_score") or 0), int(item.get("_source_priority") or 0), str(item.get("remark") or "")), reverse=True)
    test_limit = max(1, int(settings.RU_LTE_TEST_LIMIT or 40))
    tested: List[Dict[str, Any]] = []
    probe_errors = 0
    for candidate in candidates[:test_limit]:
        probe = _ru_lte_probe_candidate(candidate)
        if not probe.get("ok"):
            probe_errors += 1
            continue
        normalized = dict(candidate)
        normalized["_probe_ok"] = True
        normalized["_latency_ms"] = int(probe.get("latency_ms") or 0)
        normalized["_score"] = _ru_lte_payload_score(normalized)
        tested.append(normalized)

    tested.sort(key=lambda item: (int(item.get("_latency_ms") or 999999), -int(item.get("_source_priority") or 0), -int(item.get("_score") or 0), str(item.get("remark") or "")))
    top = tested[: max(1, int(settings.RU_LTE_MAX_CANDIDATES or 4))]

    existing_by_code = {str(row.get("code") or ""): row for row in list_locations(active_only=False)}
    assigned: List[Dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()
    remarks = {
        "ru-lte": "Russia LTE",
        "ru-lte-reserve-1": "Russia LTE | Reserve 1",
        "ru-lte-reserve-2": "Russia LTE | Reserve 2",
        "ru-lte-reserve-3": "Russia LTE | Reserve 3",
    }

    for idx, code in enumerate(RU_LTE_LOCATION_CODES):
        payload = dict(top[idx]) if idx < len(top) else {}
        if payload:
            for key in ["_score", "_source", "_probe_ok"]:
                payload.pop(key, None)
            latency_ms = int(payload.pop("_latency_ms", 0) or 0)
            payload["location_code"] = code
            payload["remark"] = remarks.get(code, code)
            updates = {
                "vpn_payload": payload,
                "status": "online",
                "is_active": True,
                "is_recommended": code == "ru-lte",
                "is_reserve": code != "ru-lte",
                "ping_ms": latency_ms if latency_ms > 0 else None,
                "speed_checked_at": now_iso,
            }
            row = _patch_location_by_code(code, updates)
            assigned.append({
                "code": code,
                "server": payload.get("server"),
                "transport": payload.get("transport"),
                "remark": payload.get("remark"),
                "latency_ms": latency_ms,
                "updated": bool(row),
                "kept_old": False,
            })
        else:
            existing = existing_by_code.get(code) or {}
            existing_payload = _compose_vpn_payload_for_location(dict(existing)) if existing else None
            if existing_payload and _config_is_complete(existing_payload):
                _patch_location_by_code(code, {
                    "status": "online",
                    "is_active": True,
                    "is_recommended": code == "ru-lte",
                    "is_reserve": code != "ru-lte",
                })
                assigned.append({
                    "code": code,
                    "server": existing_payload.get("server"),
                    "transport": existing_payload.get("transport"),
                    "remark": remarks.get(code, code),
                    "latency_ms": existing.get("ping_ms"),
                    "updated": True,
                    "kept_old": True,
                })
            else:
                row = _patch_location_by_code(code, {
                    "status": "offline",
                    "is_active": True,
                    "is_recommended": False,
                    "is_reserve": code != "ru-lte",
                })
                assigned.append({"code": code, "server": None, "transport": None, "remark": None, "latency_ms": None, "updated": bool(row), "kept_old": False})

    return {
        "ok": bool(top),
        "sources": source_stats,
        "candidates_total": len(candidates),
        "tested_total": min(len(candidates), test_limit),
        "live_total": len(tested),
        "probe_errors": probe_errors,
        "selected": assigned,
        "auto_refresh_enabled": bool(settings.RU_LTE_AUTO_REFRESH_ENABLED),
        "auto_refresh_minutes": max(1, int(settings.RU_LTE_AUTO_REFRESH_MINUTES or 30)),
    }


def refresh_black_locations() -> Dict[str, Any]:
    sources = [item for item in (settings.BLACK_SOURCE_URLS or []) if str(item or "").strip()]
    candidates: List[Dict[str, Any]] = []
    seen: set[str] = set()
    source_stats: List[Dict[str, Any]] = []

    for source in sources:
        stat = {"source": source, "lines": 0, "accepted": 0, "error": None}
        try:
            content = _read_text_from_source(source)
            for line in content.splitlines():
                stat["lines"] += 1
                payload = _parse_vless_subscription_line(line)
                if not payload:
                    continue
                normalized = _normalize_vpn_payload_keys(payload)
                if not _config_is_complete(normalized):
                    continue
                if not _black_transport_allowed(normalized):
                    continue
                key = "|".join([
                    str(normalized.get("server") or ""),
                    str(normalized.get("port") or ""),
                    str(normalized.get("uuid") or ""),
                    str(normalized.get("public_key") or ""),
                    str(normalized.get("short_id") or ""),
                    str(normalized.get("server_name") or normalized.get("sni") or ""),
                    str(normalized.get("path") or ""),
                    str(normalized.get("service_name") or ""),
                ])
                if key in seen:
                    continue
                seen.add(key)
                normalized["_source"] = source
                normalized["_source_priority"] = _black_source_priority(source)
                normalized["_score"] = _ru_lte_payload_score(normalized)
                candidates.append(normalized)
                stat["accepted"] += 1
        except Exception as exc:
            stat["error"] = str(exc)
        source_stats.append(stat)

    candidates.sort(key=lambda item: (int(item.get("_score") or 0), int(item.get("_source_priority") or 0), str(item.get("remark") or "")), reverse=True)
    test_limit = max(1, int(settings.BLACK_TEST_LIMIT or 40))
    tested: List[Dict[str, Any]] = []
    probe_errors = 0
    for candidate in candidates[:test_limit]:
        probe = _black_probe_candidate(candidate)
        if not probe.get("ok"):
            probe_errors += 1
            continue
        normalized = dict(candidate)
        normalized["_probe_ok"] = True
        normalized["_latency_ms"] = int(probe.get("latency_ms") or 0)
        normalized["_score"] = _ru_lte_payload_score(normalized)
        tested.append(normalized)

    tested.sort(key=lambda item: (int(item.get("_latency_ms") or 999999), -int(item.get("_source_priority") or 0), -int(item.get("_score") or 0), str(item.get("remark") or "")))
    top = tested[: max(1, int(settings.BLACK_MAX_CANDIDATES or 4))]

    existing_by_code = {str(row.get("code") or ""): row for row in list_locations(active_only=False)}
    assigned: List[Dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()
    remarks = {
        "intl-fast": "Fast / International",
        "intl-fast-reserve-1": "Fast / International | Reserve 1",
        "intl-fast-reserve-2": "Fast / International | Reserve 2",
        "intl-fast-reserve-3": "Fast / International | Reserve 3",
    }

    for idx, code in enumerate(BLACK_LOCATION_CODES):
        payload = dict(top[idx]) if idx < len(top) else {}
        if payload:
            for key in ["_score", "_source", "_probe_ok"]:
                payload.pop(key, None)
            latency_ms = int(payload.pop("_latency_ms", 0) or 0)
            payload["location_code"] = code
            payload["remark"] = remarks.get(code, code)
            updates = {
                "name_ru": remarks.get(code, code),
                "name_en": remarks.get(code, code),
                "country_code": None,
                "vpn_payload": payload,
                "status": "online",
                "is_active": True,
                "is_recommended": False,
                "is_reserve": code != "intl-fast",
                "ping_ms": latency_ms if latency_ms > 0 else None,
                "speed_checked_at": now_iso,
            }
            row = _patch_location_by_code(code, updates)
            assigned.append({
                "code": code,
                "server": payload.get("server"),
                "transport": payload.get("transport"),
                "security": payload.get("security"),
                "remark": payload.get("remark"),
                "latency_ms": latency_ms,
                "updated": bool(row),
                "kept_old": False,
            })
        else:
            existing = existing_by_code.get(code) or {}
            existing_payload = _compose_vpn_payload_for_location(dict(existing)) if existing else None
            if existing_payload and _config_is_complete(existing_payload):
                _patch_location_by_code(code, {
                    "name_ru": remarks.get(code, code),
                    "name_en": remarks.get(code, code),
                    "country_code": None,
                    "status": "online",
                    "is_active": True,
                    "is_recommended": False,
                    "is_reserve": code != "intl-fast",
                })
                assigned.append({
                    "code": code,
                    "server": existing_payload.get("server"),
                    "transport": existing_payload.get("transport"),
                    "security": existing_payload.get("security"),
                    "remark": remarks.get(code, code),
                    "latency_ms": existing.get("ping_ms"),
                    "updated": True,
                    "kept_old": True,
                })
            else:
                row = _patch_location_by_code(code, {
                    "name_ru": remarks.get(code, code),
                    "name_en": remarks.get(code, code),
                    "country_code": None,
                    "status": "offline",
                    "is_active": True,
                    "is_recommended": False,
                    "is_reserve": code != "intl-fast",
                })
                assigned.append({"code": code, "server": None, "transport": None, "security": None, "remark": None, "latency_ms": None, "updated": bool(row), "kept_old": False})

    return {
        "ok": bool(top),
        "sources": source_stats,
        "candidates_total": len(candidates),
        "tested_total": min(len(candidates), test_limit),
        "live_total": len(tested),
        "probe_errors": probe_errors,
        "selected": assigned,
        "auto_refresh_enabled": bool(settings.BLACK_AUTO_REFRESH_ENABLED),
        "auto_refresh_minutes": max(1, int(settings.BLACK_AUTO_REFRESH_MINUTES or 30)),
    }


@app.on_event("startup")
def on_startup() -> None:
    bootstrap()
    if settings.RU_LTE_REFRESH_ON_STARTUP:
        try:
            _run_ru_lte_refresh_safe(source="startup")
        except Exception as exc:
            _set_ru_lte_refresh_error(exc)
    if settings.BLACK_REFRESH_ON_STARTUP:
        try:
            _run_black_refresh_safe(source="startup")
        except Exception as exc:
            _set_black_refresh_error(exc)
    _start_ru_lte_auto_refresh_loop()
    _start_black_auto_refresh_loop()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.CORS_ORIGINS == ["*"] else settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=500)

_LOCATIONS_CACHE_TTL_SEC = 15
_locations_cache: Dict[str, Any] = {"expires_at": 0.0, "items": None}
_ru_lte_refresh_state: Dict[str, Any] = {"last_success_at": None, "last_error": None, "last_error_at": None}
_black_refresh_state: Dict[str, Any] = {"last_success_at": None, "last_error": None, "last_error_at": None}


def _invalidate_locations_cache() -> None:
    _locations_cache["items"] = None
    _locations_cache["expires_at"] = 0.0


def _set_ru_lte_refresh_success() -> None:
    _ru_lte_refresh_state["last_success_at"] = datetime.now(timezone.utc).isoformat()
    _ru_lte_refresh_state["last_error"] = None
    _ru_lte_refresh_state["last_error_at"] = None


def _set_ru_lte_refresh_error(exc: Exception) -> None:
    _ru_lte_refresh_state["last_error"] = str(exc)
    _ru_lte_refresh_state["last_error_at"] = datetime.now(timezone.utc).isoformat()


def _run_ru_lte_refresh_safe(*, source: str = "manual") -> Dict[str, Any]:
    result = refresh_ru_lte_locations()
    result["refresh_source"] = source
    _invalidate_locations_cache()
    _set_ru_lte_refresh_success()
    return result


def _start_ru_lte_auto_refresh_loop() -> None:
    if not settings.RU_LTE_AUTO_REFRESH_ENABLED:
        return
    interval_minutes = max(1, int(settings.RU_LTE_AUTO_REFRESH_MINUTES or 30))
    timeout_seconds = max(60, int(settings.RU_LTE_AUTO_REFRESH_TIMEOUT_SEC or 600))

    def worker() -> None:
        while True:
            try:
                _run_ru_lte_refresh_safe(source="auto")
            except Exception as exc:
                _set_ru_lte_refresh_error(exc)
            time.sleep(timeout_seconds if timeout_seconds > interval_minutes * 60 else interval_minutes * 60)

    thread = threading.Thread(target=worker, name="ru-lte-auto-refresh", daemon=True)
    thread.start()


def _set_black_refresh_success() -> None:
    _black_refresh_state["last_success_at"] = datetime.now(timezone.utc).isoformat()
    _black_refresh_state["last_error"] = None
    _black_refresh_state["last_error_at"] = None


def _set_black_refresh_error(exc: Exception) -> None:
    _black_refresh_state["last_error"] = str(exc)
    _black_refresh_state["last_error_at"] = datetime.now(timezone.utc).isoformat()


def _run_black_refresh_safe(*, source: str = "manual") -> Dict[str, Any]:
    result = refresh_black_locations()
    result["refresh_source"] = source
    _invalidate_locations_cache()
    _set_black_refresh_success()
    return result


def _start_black_auto_refresh_loop() -> None:
    if not settings.BLACK_AUTO_REFRESH_ENABLED:
        return
    interval_minutes = max(1, int(settings.BLACK_AUTO_REFRESH_MINUTES or 30))
    timeout_seconds = max(60, int(settings.BLACK_AUTO_REFRESH_TIMEOUT_SEC or 600))

    def worker() -> None:
        while True:
            try:
                _run_black_refresh_safe(source="auto")
            except Exception as exc:
                _set_black_refresh_error(exc)
            time.sleep(timeout_seconds if timeout_seconds > interval_minutes * 60 else interval_minutes * 60)

    thread = threading.Thread(target=worker, name="black-auto-refresh", daemon=True)
    thread.start()


def _cached_locations_payload() -> List[Dict[str, Any]]:
    now = time.monotonic()
    cached_items = _locations_cache.get("items")
    expires_at = float(_locations_cache.get("expires_at") or 0.0)
    if cached_items is not None and expires_at > now:
        return cached_items
    items = [serialize_location(row) for row in list_locations(active_only=True)]
    _locations_cache["items"] = items
    _locations_cache["expires_at"] = now + _LOCATIONS_CACHE_TTL_SEC
    return items



def _safe_compare_secret(left: Optional[str], right: Optional[str]) -> bool:
    left_bytes = (left or "").encode("utf-8")
    right_bytes = (right or "").encode("utf-8")
    return secrets.compare_digest(left_bytes, right_bytes)


def issue_token(user_id: int, *, expires_delta: timedelta, token_type: str = "access") -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "typ": token_type,
        "iat": now,
        "exp": now + expires_delta,
        "jti": uuid4().hex,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")



def issue_access_token(user_id: int) -> str:
    return issue_token(
        user_id,
        expires_delta=timedelta(minutes=max(1, int(settings.AUTH_ACCESS_TOKEN_MINUTES or 60))),
        token_type="access",
    )



def issue_refresh_token(user_id: int) -> str:
    return issue_token(
        user_id,
        expires_delta=timedelta(days=max(1, int(settings.AUTH_REFRESH_TOKEN_DAYS or 90))),
        token_type="refresh",
    )



def _decode_token(raw_token: str, *, expected_type: Optional[str] = None) -> Dict[str, Any]:
    try:
        payload = jwt.decode(raw_token, settings.JWT_SECRET, algorithms=["HS256"])
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    token_type = str(payload.get("typ") or "")
    if expected_type and token_type != expected_type:
        raise HTTPException(status_code=401, detail=f"Invalid token type: expected {expected_type}")
    return payload



def _issue_auth_payload(user: Dict[str, Any], *, is_new: bool = False) -> Dict[str, Any]:
    user_id = int(user["id"])
    refresh_subscription_statuses(user_id)
    fresh_user = get_user_by_id(user_id) or user
    access_token = issue_access_token(user_id)
    refresh_token = issue_refresh_token(user_id)
    view = get_user_subscription_view(user_id)
    return {
        "ok": True,
        "token": access_token,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": fresh_user,
        "subscription": view.get("subscription"),
        "language": fresh_user.get("language") or "ru",
        "is_new": is_new,
    }



def _fallback_code_user_payload(payload: CodeAuthIn) -> Dict[str, Any]:
    suffix = str(payload.code or settings.AUTH_DEV_LOGIN_CODE)[-6:]
    telegram_id = payload.telegram_id or int(f"900{suffix}")
    language = "en" if payload.language == "en" else "ru"
    return {
        "telegram_id": telegram_id,
        "username": payload.username or f"inet_dev_{suffix}",
        "first_name": payload.first_name or "INET",
        "last_name": payload.last_name or "Dev",
        "language": language,
    }



def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    payload = _decode_token(credentials.credentials, expected_type="access")
    user_id = int(payload["sub"])
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user



def require_code_issuer(x_auth_code_secret: Optional[str] = Header(default=None)) -> bool:
    configured_secret = (settings.AUTH_CODE_ISSUER_SECRET or "").strip()
    if not configured_secret:
        return True
    if _safe_compare_secret(x_auth_code_secret, configured_secret):
        return True
    raise HTTPException(status_code=401, detail="Invalid code issuer secret")



def require_admin(credentials: HTTPBasicCredentials = Depends(basic_security)) -> str:
    valid_user = _safe_compare_secret(credentials.username, settings.ADMIN_BASIC_USER)
    valid_pass = _safe_compare_secret(credentials.password, settings.ADMIN_BASIC_PASS)
    if not (valid_user and valid_pass):
        raise HTTPException(status_code=401, detail="Invalid admin credentials", headers={"WWW-Authenticate": "Basic"})
    return credentials.username


def _flag_emoji(country_code: Optional[str]) -> str:
    if not country_code or len(country_code) != 2:
        return ""
    code = country_code.upper()
    if not code.isalpha():
        return ""
    return "".join(chr(127397 + ord(char)) for char in code)



def _location_meta(row: Dict[str, Any]) -> Dict[str, Any]:
    code = str(row.get("code") or "")
    country_code = row.get("country_code")
    if code.startswith("auto-"):
        return {
            "type": "virtual",
            "section_key": "system",
            "section_name_ru": "Системные",
            "section_name_en": "System",
            "icon": "💎",
        }
    if "lte" in code.lower():
        return {
            "type": "mobile",
            "section_key": "mobile",
            "section_name_ru": "Мобильные",
            "section_name_en": "Mobile",
            "icon": "📶",
        }
    return {
        "type": "node",
        "section_key": "countries",
        "section_name_ru": "Основные страны",
        "section_name_en": "Main countries",
        "icon": _flag_emoji(country_code),
    }



def _diagnostic_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()



def _diagnostic_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return None



def _diagnostic_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0



def _diagnostic_placeholder(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    lowered = text.lower()
    if lowered.startswith(("paste_", "your_", "replace_", "todo", "changeme")):
        return True
    if "example.com" in lowered or "example.net" in lowered or "example.org" in lowered:
        return True
    if lowered in {"ru_provider_host", "uz_provider_host", "ru_provider_user", "uz_provider_user", "ru_provider_pass", "uz_provider_pass"}:
        return True
    return False


def _diagnostic_string_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return []



def _build_tun_platform_diagnostics(payload: Dict[str, Any], platform_label: str) -> Dict[str, Any]:
    issues: List[str] = []
    fixes: List[str] = []

    server = _diagnostic_text(payload.get("server"))
    port = _diagnostic_int(payload.get("port"))
    uuid = _diagnostic_text(payload.get("uuid"))
    security = _diagnostic_text(payload.get("security") or "reality").lower() or "reality"
    transport = _diagnostic_text(payload.get("transport") or payload.get("network") or "tcp").lower() or "tcp"
    sni = _diagnostic_text(payload.get("server_name") or payload.get("sni"))
    public_key = _diagnostic_text(payload.get("public_key") or payload.get("publicKey"))
    short_id = _diagnostic_text(payload.get("short_id") or payload.get("shortId"))
    service_name = _diagnostic_text(payload.get("service_name") or payload.get("serviceName"))
    path = _diagnostic_text(payload.get("path"))
    connect_mode = _diagnostic_text(payload.get("connect_mode") or "tun").lower() or "tun"
    full_tunnel = _diagnostic_bool(payload.get("full_tunnel"))
    dns_servers = _diagnostic_string_list(payload.get("dns_servers") or payload.get("dnsServers"))

    if not payload:
        issues.append("vpn_payload is empty")
        fixes.append("Open Edit payload and fill server, port, uuid, and Reality fields.")

    if not server or _diagnostic_placeholder(server):
        issues.append("server is missing or still contains a placeholder")
    if port <= 0:
        issues.append("port is missing")
    if not uuid or _diagnostic_placeholder(uuid):
        issues.append("uuid is missing or still contains a placeholder")

    if any(issue in {"server is missing or still contains a placeholder", "port is missing", "uuid is missing or still contains a placeholder"} for issue in issues):
        fixes.append("Set real server/port/uuid values in effective payload.")

    if security == "reality":
        if not public_key or _diagnostic_placeholder(public_key):
            issues.append("Reality public_key is missing or still contains a placeholder")
        if not sni or _diagnostic_placeholder(sni):
            issues.append("Reality server_name / sni is missing or still contains a placeholder")
        if not short_id or _diagnostic_placeholder(short_id):
            issues.append("Reality short_id is missing or still contains a placeholder")
        if any(issue.startswith("Reality ") for issue in issues):
            fixes.append("For Reality fill real public_key, short_id, and server_name/sni values.")

    if transport in {"grpc"} and (not service_name or _diagnostic_placeholder(service_name)):
        issues.append("gRPC service_name is missing or still contains a placeholder")
        fixes.append("Set service_name for gRPC transport.")

    if transport in {"ws", "websocket"} and (not path or _diagnostic_placeholder(path)):
        issues.append("WebSocket path is missing or still contains a placeholder")
        fixes.append("Set path for WebSocket transport.")

    if connect_mode != "tun":
        issues.append(f"connect_mode must be tun, got {connect_mode or 'empty'}")
        fixes.append("Set connect_mode=tun.")

    if full_tunnel is False:
        issues.append("full_tunnel is disabled")
        fixes.append("Set full_tunnel=true for full-device routing.")

    if not dns_servers or any(_diagnostic_placeholder(item) for item in dns_servers):
        issues.append("dns_servers is empty or still contains placeholders")
        fixes.append("Add dns_servers, for example 1.1.1.1 and 8.8.8.8.")

    fatal_prefixes = (
        "vpn_payload is empty",
        "server is missing or still contains a placeholder",
        "port is missing",
        "uuid is missing or still contains a placeholder",
        "Reality public_key is missing or still contains a placeholder",
        "Reality server_name / sni is missing or still contains a placeholder",
        "Reality short_id is missing or still contains a placeholder",
        "connect_mode must be tun",
    )
    fatal_issues = [issue for issue in issues if issue.startswith(fatal_prefixes)]

    if fatal_issues:
        status = "error"
        label = f"{platform_label}: payload incomplete"
    elif issues:
        status = "warning"
        label = f"{platform_label}: check payload"
    else:
        status = "ready"
        label = f"{platform_label}: ready"

    if not issues and not _config_is_complete(payload):
        status = "error"
        label = f"{platform_label}: payload incomplete"
        issues.append("effective payload is incomplete")
        fixes.append("Fill required fields in effective payload.")

    unique_fixes = list(dict.fromkeys([item for item in fixes if item]))
    return {
        "status": status,
        "label": label,
        "issues": issues,
        "fixes": unique_fixes,
    }



def build_location_tun_diagnostics(row: Dict[str, Any], *, resolved_payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = resolved_payload if isinstance(resolved_payload, dict) else _compose_vpn_payload_for_location(dict(row))
    android = _build_tun_platform_diagnostics(payload, "Android")
    ios = _build_tun_platform_diagnostics(payload, "iOS")

    summary_status = "ready"
    if android["status"] == "error" or ios["status"] == "error":
        summary_status = "error"
    elif android["status"] == "warning" or ios["status"] == "warning":
        summary_status = "warning"

    issues = list(dict.fromkeys(android.get("issues", []) + ios.get("issues", [])))
    fixes = list(dict.fromkeys(android.get("fixes", []) + ios.get("fixes", [])))
    if summary_status == "ready":
        summary_text = "TUN payload is ready for Android and iOS."
    else:
        summary_text = "; ".join(issues[:4]) or "TUN payload needs attention."

    return {
        "summary_status": summary_status,
        "summary_text": summary_text,
        "issues": issues,
        "fixes": fixes,
        "android": android,
        "ios": ios,
    }



def _location_error_created_at(row: Dict[str, Any]) -> str:
    for key in ("updated_at", "created_at"):
        value = row.get(key)
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).isoformat()
        text = _diagnostic_text(value)
        if text:
            return text
    return datetime.now(timezone.utc).isoformat()



def build_location_tun_error_items() -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for row in list_locations(active_only=False):
        diagnostics = build_location_tun_diagnostics(row)
        if diagnostics.get("summary_status") == "ready":
            continue
        code = _diagnostic_text(row.get("code")) or "unknown"
        issues = diagnostics.get("issues", [])
        fixes = diagnostics.get("fixes", [])
        message_parts = []
        if issues:
            message_parts.append("Issues: " + " | ".join(issues[:4]))
        if fixes:
            message_parts.append("Fix: " + " | ".join(fixes[:3]))
        items.append({
            "created_at": _location_error_created_at(row),
            "source": f"vpn-location:{code}",
            "context": diagnostics.get("summary_status") or "error",
            "error_message": " || ".join(message_parts) or (diagnostics.get("summary_text") or "TUN payload needs attention."),
        })
    return items



def serialize_location(row: Dict[str, Any], *, include_payload: bool = False) -> Dict[str, Any]:
    item = dict(row)
    raw_vpn_payload = item.pop("vpn_payload", None)
    normalized_payload = dict(raw_vpn_payload) if isinstance(raw_vpn_payload, dict) else {}
    item["has_vpn_payload"] = bool(normalized_payload)
    meta = _location_meta(item)
    item.update(meta)
    item["display_name_ru"] = f'{meta["icon"]} {item.get("name_ru")}'.strip() if meta.get("icon") else item.get("name_ru")
    item["display_name_en"] = f'{meta["icon"]} {item.get("name_en")}'.strip() if meta.get("icon") else item.get("name_en")
    item["name"] = item.get("display_name_ru") or item.get("name_ru") or item.get("name_en")
    item["recommended"] = bool(item.get("is_recommended"))
    item["reserve"] = bool(item.get("is_reserve"))
    item["location_source"] = str(item.get("location_source") or "catalog")
    resolved_payload = _compose_vpn_payload_for_location(dict(row))
    item["vpn_payload_complete"] = bool(resolved_payload) and _config_is_complete(resolved_payload)
    if include_payload:
        item["vpn_payload"] = normalized_payload
        item["resolved_vpn_payload"] = resolved_payload
        item["tun_diagnostics"] = build_location_tun_diagnostics(row, resolved_payload=resolved_payload)
    return item



def _bot_public_url() -> str:
    bot_username = (settings.BOT_USERNAME or "").strip().lstrip("@")
    if bot_username:
        return f"https://t.me/{bot_username}"
    return settings.SUPPORT_TELEGRAM_URL


def _subscription_public_url_from_base(base_url: str, token: Optional[str]) -> Optional[str]:
    base = str(base_url or "").strip().rstrip("/")
    clean_token = str(token or "").strip()
    if not base or not clean_token:
        return None
    return f"{base}/sub/{quote(clean_token, safe='')}"


def _resolve_subscription_token(*, token: Optional[str] = None, code: Optional[str] = None) -> Optional[str]:
    clean_token = str(token or "").strip()
    if clean_token:
        return clean_token
    clean_code = str(code or "").strip()
    if not clean_code:
        return None
    user = get_user_by_active_auth_code(clean_code)
    if not user:
        return None
    return ensure_user_subscription_token(int(user["id"]))


def _subscription_public_url(request: Optional[Request] = None, token: Optional[str] = None, code: Optional[str] = None) -> Optional[str]:
    clean_token = _resolve_subscription_token(token=token, code=code)
    if not clean_token:
        return None
    if request is not None:
        try:
            return str(request.url_for("public_subscription", token=clean_token))
        except Exception:
            pass
    return _subscription_public_url_from_base(settings.BACKEND_BASE_URL, clean_token)


def _build_native_open_app_url(request: Optional[Request] = None, *, code: Optional[str] = None, token: Optional[str] = None, lang: Optional[str] = None) -> str:
    del lang
    subscription_url = _subscription_public_url(request, token=token, code=code)
    if not subscription_url:
        return ""
    import_name = str(getattr(settings, "HIDDIFY_IMPORT_NAME", "") or f"{settings.APP_NAME} Subscription").strip()
    return f"hiddify://import/{quote(subscription_url, safe=':/?&=%')}#{quote(import_name, safe='')}"


def _build_open_app_bridge_url(request: Request, *, code: Optional[str] = None, token: Optional[str] = None, lang: Optional[str] = None) -> str:
    bridge = (settings.OPEN_APP_BRIDGE_URL or "").strip()
    if bridge:
        parts = urlsplit(bridge)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        if code:
            query["code"] = code
        elif token:
            query["token"] = token
        if lang:
            query["lang"] = lang
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    try:
        return str(request.url_for("open_app_bridge", code=code or "", token=token or "", lang=lang or "ru"))
    except Exception:
        base = str(request.base_url).rstrip("/")
        query = {}
        if code:
            query["code"] = code
        elif token:
            query["token"] = token
        if lang:
            query["lang"] = lang
        return f"{base}/open-app?{urlencode(query)}" if query else f"{base}/open-app"


def _detect_android_app_package() -> str:
    explicit = str(getattr(settings, "ANDROID_APP_PACKAGE", "") or "").strip()
    if explicit:
        return explicit
    parsed = urlsplit(str(settings.ANDROID_APP_URL or "").strip())
    if parsed.scheme and parsed.netloc:
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        package_name = str(query.get("id") or "").strip()
        if package_name:
            return package_name
    return ""


def _build_android_intent_url(native_url: str) -> str:
    parsed_native = urlsplit(native_url)
    if not parsed_native.scheme or parsed_native.scheme in {"http", "https"}:
        return ""
    android_package = _detect_android_app_package()
    if not android_package:
        return ""
    intent_path = parsed_native.path or ""
    if parsed_native.netloc:
        intent_path = f"//{parsed_native.netloc}{intent_path}"
    intent_query = f"?{parsed_native.query}" if parsed_native.query else ""
    intent_fragment = f"#{parsed_native.fragment}" if parsed_native.fragment else ""
    return (
        f"intent:{intent_path}{intent_query}{intent_fragment}"
        f"#Intent;scheme={parsed_native.scheme};package={android_package};end"
    )


def _subscription_access_context(token: str) -> Optional[Dict[str, Any]]:
    provided = str(token or "").strip()
    if not provided:
        return None
    expected = str(settings.SUBSCRIPTION_TOKEN or "").strip()
    if settings.LEGACY_GLOBAL_SUBSCRIPTION_TOKEN_ENABLED and expected and secrets.compare_digest(provided, expected):
        return {"kind": "global", "user": None}
    user = get_user_by_subscription_token(provided)
    if user:
        return {"kind": "user", "user": user}
    return None



def _subscription_token_is_active(token: Optional[str]) -> bool:
    access = _subscription_access_context(str(token or "").strip())
    if not access:
        return False
    if access["kind"] != "user":
        return True
    user = access.get("user")
    if not user or user.get("status") == "blocked":
        return False
    view = get_user_subscription_view(int(user["id"]))
    return bool(view.get("is_active") and view.get("subscription"))



def _sanitize_tracking_value(value: Optional[str], *, max_len: int = 160) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    cleaned = ''.join(ch for ch in raw if ch.isalnum() or ch in {'-', '_', '.', ':', '@'})
    return cleaned[:max_len]



def _detect_device_platform_and_name(request: Request) -> Tuple[str, str]:
    user_agent = str(request.headers.get("user-agent") or "").strip()
    ua = user_agent.lower()
    sec_platform = str(request.headers.get("sec-ch-ua-platform") or "").strip().strip('"').lower()
    platform = "client"
    if "android" in ua or sec_platform == "android":
        platform = "android"
    elif any(token in ua for token in ("iphone", "ipad", "ios")) or sec_platform in {"ios", "iphone", "ipad"}:
        platform = "ios"
    elif "windows" in ua:
        platform = "windows"
    elif any(token in ua for token in ("mac os", "macos", "darwin")):
        platform = "macos"
    elif "linux" in ua:
        platform = "linux"

    client_name = "VPN client"
    if "hiddify" in ua:
        client_name = "Hiddify"
    elif "nekobox" in ua:
        client_name = "NekoBox"
    elif "nekoray" in ua:
        client_name = "NekoRay"
    elif "sing-box" in ua or "singbox" in ua:
        client_name = "sing-box"

    platform_title = {
        "android": "Android",
        "ios": "iOS",
        "windows": "Windows",
        "macos": "macOS",
        "linux": "Linux",
    }.get(platform)
    device_name = f"{client_name} {platform_title}" if platform_title else client_name
    return platform, device_name



def _client_ip_from_request(request: Request) -> str:
    for header_name in ("cf-connecting-ip", "x-real-ip", "x-forwarded-for"):
        raw = str(request.headers.get(header_name) or "").strip()
        if raw:
            return raw.split(",", 1)[0].strip()
    client = getattr(request, "client", None)
    host = getattr(client, "host", None)
    return str(host or "").strip()



def _build_subscription_device_fingerprint(request: Request, token: str, client_id: Optional[str] = None) -> Optional[str]:
    normalized_client_id = _sanitize_tracking_value(client_id, max_len=120)
    if normalized_client_id:
        source = f"cid:{normalized_client_id}"
    else:
        user_agent = str(request.headers.get("user-agent") or "").strip()
        accept_language = str(request.headers.get("accept-language") or "").strip()
        sec_platform = str(request.headers.get("sec-ch-ua-platform") or "").strip()
        client_ip = _client_ip_from_request(request)
        parts = [user_agent, accept_language, sec_platform, client_ip]
        if not any(part.strip() for part in parts):
            return None
        source = "fallback:" + "|".join(part.strip() for part in parts)
    return hashlib.sha256(f"sub-device:v2:{token}:{source}".encode("utf-8")).hexdigest()



def _track_subscription_device_access(request: Request, token: str, access: Optional[Dict[str, Any]]) -> None:
    if not access or access.get("kind") != "user":
        return
    user = access.get("user") or {}
    if not user or user.get("status") == "blocked":
        return
    client_id = request.query_params.get("cid") or request.headers.get("x-client-id")
    fingerprint = _build_subscription_device_fingerprint(request, token, client_id)
    if not fingerprint:
        return
    platform, device_name = _detect_device_platform_and_name(request)
    try:
        touch_subscription_device_by_token(token, platform=platform, device_name=device_name, device_fingerprint=fingerprint)
    except Exception:
        pass



def _subscription_device_gate(request: Request, token: str, access: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not access or access.get("kind") != "user":
        return None
    user = access.get("user") or {}
    if not user or user.get("status") == "blocked":
        return None
    client_id = request.query_params.get("cid") or request.headers.get("x-client-id")
    fingerprint = _build_subscription_device_fingerprint(request, token, client_id)
    if not fingerprint:
        return None
    try:
        return get_subscription_device_gate_by_token(token, fingerprint)
    except Exception:
        return None



def _build_vless_subscription_line(payload: Dict[str, Any], *, fallback_name: str = "VLESS") -> str:
    normalized = _normalize_vpn_payload_keys(payload)
    if not normalized or not _config_is_complete(normalized):
        raise ValueError("VLESS payload is incomplete")

    uuid = str(normalized.get("uuid") or "").strip()
    server = str(normalized.get("server") or "").strip()
    port = int(normalized.get("port") or 443)
    remark = str(normalized.get("remark") or normalized.get("display_name") or fallback_name).strip() or fallback_name

    query: Dict[str, Any] = {
        "type": str(normalized.get("transport") or normalized.get("network") or "tcp").strip() or "tcp",
        "security": str(normalized.get("security") or "reality").strip() or "reality",
    }
    optional_keys = {
        "flow": normalized.get("flow"),
        "sni": normalized.get("sni") or normalized.get("server_name"),
        "host": normalized.get("host"),
        "path": normalized.get("path"),
        "serviceName": normalized.get("service_name") or normalized.get("serviceName"),
        "pbk": normalized.get("public_key") or normalized.get("publicKey"),
        "sid": normalized.get("short_id") or normalized.get("shortId"),
        "fp": normalized.get("fingerprint"),
        "alpn": ",".join(str(item).strip() for item in (normalized.get("alpn") or []) if str(item).strip()),
        "packetEncoding": normalized.get("packet_encoding") or normalized.get("packetEncoding"),
    }
    for key, value in optional_keys.items():
        text = str(value or "").strip()
        if text:
            query[key] = text

    return f"vless://{quote(uuid, safe='')}@{server}:{port}?{urlencode(query)}#{quote(remark, safe='')}"



def _subscription_location_rows() -> List[Dict[str, Any]]:
    concrete: List[Dict[str, Any]] = []
    for row in list_locations(active_only=True):
        code = str(row.get("code") or "").strip()
        if code in {"auto-fastest", "auto-reserve"}:
            continue
        if str(row.get("status") or "").strip().lower() != "online":
            continue
        payload = _compose_vpn_payload_for_location(dict(row))
        if payload and _config_is_complete(payload):
            concrete.append(dict(row))
    priority = {
        "ru-lte": 0,
        "ru-lte-reserve-1": 1,
        "ru-lte-reserve-2": 2,
        "ru-lte-reserve-3": 3,
        "se": 4,
    }
    concrete.sort(key=lambda row: (priority.get(str(row.get("code") or ""), 1000), int(row.get("sort_order") or 9999), str(row.get("name_en") or row.get("code") or "")))
    return concrete


@app.get("/sub/{token}")
def public_subscription(request: Request, token: str, cid: Optional[str] = Query(default=None)) -> Response:
    del cid
    access = _subscription_access_context(token)
    if not access:
        raise HTTPException(status_code=404, detail="Subscription not found")

    expires_ts = int(time.time()) + 86400 * 3650
    profile_title = f"{settings.APP_NAME} Subscription"
    if access["kind"] == "user":
        user = access["user"]
        if not user or user.get("status") == "blocked":
            raise HTTPException(status_code=404, detail="Subscription not found")
        view = get_user_subscription_view(int(user["id"]))
        if not view.get("is_active") or not view.get("subscription"):
            raise HTTPException(status_code=403, detail="Active subscription required")
        subscription = view["subscription"] or {}
        expires_at = subscription.get("expires_at")
        if isinstance(expires_at, datetime):
            expires_ts = int(expires_at.timestamp())
        elif isinstance(expires_at, str):
            try:
                expires_ts = int(datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp())
            except Exception:
                pass
        profile_title = f"{settings.APP_NAME} · {user.get('telegram_id')}"

        gate = _subscription_device_gate(request, token, access)
        if gate and not gate.get("allowed"):
            used = int(gate.get("devices_used") or 0)
            limit = int(gate.get("device_limit") or 0)
            content = (
                f"Device limit reached ({used}/{limit}). Remove one device in the bot or admin panel and try again.\n"
                f"Лимит устройств исчерпан ({used}/{limit}). Удалите одно устройство в боте или админке и попробуйте снова.\n"
            )
            return Response(content=content, status_code=403, media_type="text/plain; charset=utf-8")

    _track_subscription_device_access(request, token, access)

    rows = _subscription_location_rows()
    lines: List[str] = []
    for row in rows:
        payload = _compose_vpn_payload_for_location(dict(row))
        try:
            lines.append(_build_vless_subscription_line(payload, fallback_name=str(row.get("name_en") or row.get("name_ru") or row.get("code") or "VLESS")))
        except Exception:
            continue

    if not lines:
        raise HTTPException(status_code=503, detail="No ready VLESS locations found for subscription")

    content = "\n".join(lines) + "\n"
    headers = {
        "Content-Disposition": 'inline; filename="inet-subscription.txt"',
        "Profile-Title": quote(f"base64:{base64.b64encode(profile_title.encode('utf-8')).decode('ascii')}", safe=':='),
        "Subscription-Userinfo": f"upload=0; download=0; total=0; expire={expires_ts}",
    }
    return Response(content=content, media_type="text/plain; charset=utf-8", headers=headers)


@app.get("/sub")
def public_subscription_hint() -> Dict[str, Any]:
    return {
        "ok": True,
        "message": "Use /sub/<personal_subscription_token>",
    }


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/open-app", response_class=HTMLResponse, name="open_app_bridge")
def open_app_bridge(
    request: Request,
    code: Optional[str] = Query(default=None),
    token: Optional[str] = Query(default=None),
    lang: str = Query(default="ru"),
) -> HTMLResponse:
    norm_lang = "en" if lang == "en" else "ru"
    resolved_token = _resolve_subscription_token(token=token, code=code)
    active_token = resolved_token if _subscription_token_is_active(resolved_token) else None
    native_url = _build_native_open_app_url(request=request, code=code, token=active_token, lang=norm_lang) if active_token else ""
    subscription_url = _subscription_public_url(request, token=active_token) if active_token else None
    bot_url = _bot_public_url()
    page_text = {
        "ru": {
            "title": "Подключение через Hiddify",
            "headline": "Открываем Hiddify…",
            "body": "Hiddify должен открыться автоматически и импортировать вашу персональную подписку. Если этого не произошло, используйте кнопки ниже.",
            "invalid_link": "Ссылка недействительна или срок доступа истёк. Вернитесь в бота и купите подписку.",
            "open_button": "Открыть в Hiddify",
            "android_button": "Скачать Hiddify для Android",
            "ios_button": "Скачать Hiddify для iPhone / iPad",
            "windows_button": "Скачать Hiddify для Windows",
            "macos_button": "Скачать Hiddify для macOS",
            "copy_label": "Персональная ссылка подписки",
            "bot_button": "Вернуться в бота",
        },
        "en": {
            "title": "Connect with Hiddify",
            "headline": "Opening Hiddify…",
            "body": "Hiddify should open automatically and import your personal subscription. If it does not, use the buttons below.",
            "invalid_link": "This link is invalid or access has expired. Return to the bot and buy a subscription.",
            "open_button": "Open in Hiddify",
            "android_button": "Download Hiddify for Android",
            "ios_button": "Download Hiddify for iPhone / iPad",
            "windows_button": "Download Hiddify for Windows",
            "macos_button": "Download Hiddify for macOS",
            "copy_label": "Personal subscription link",
            "bot_button": "Back to bot",
        },
    }[norm_lang]
    copy_block = ""
    if subscription_url:
        copy_block = f'<div class="code"><div class="label">{html.escape(page_text["copy_label"])}</div><code id="subscription-link-value">{html.escape(subscription_url)}</code></div>'
    native_url_attr = html.escape(native_url or subscription_url or "", quote=True)
    native_url_js = json.dumps(native_url)
    subscription_url_js = json.dumps(subscription_url or "")
    import_name_js = json.dumps(str(getattr(settings, "HIDDIFY_IMPORT_NAME", "") or f"{settings.APP_NAME} Subscription").strip())
    android_intent_url = _build_android_intent_url(native_url)
    android_intent_url_js = json.dumps(android_intent_url)
    android_url = html.escape(str(settings.ANDROID_APP_URL or ""), quote=True)
    android_url_js = json.dumps(str(settings.ANDROID_APP_URL or ""))
    ios_url = html.escape(str(settings.IOS_APP_URL or ""), quote=True)
    ios_url_js = json.dumps(str(settings.IOS_APP_URL or ""))
    windows_url = html.escape(str(getattr(settings, "WINDOWS_APP_URL", "") or ""), quote=True)
    macos_url = html.escape(str(getattr(settings, "MACOS_APP_URL", "") or ""), quote=True)
    bot_url_attr = html.escape(bot_url, quote=True)
    title = html.escape(page_text["title"])
    headline = html.escape(page_text["headline"])
    body_value = page_text["body"] if subscription_url else page_text["invalid_link"]
    body = html.escape(body_value)
    open_button = html.escape(page_text["open_button"])
    android_button = html.escape(page_text["android_button"])
    ios_button = html.escape(page_text["ios_button"])
    windows_button = html.escape(page_text["windows_button"])
    macos_button = html.escape(page_text["macos_button"])
    bot_button = html.escape(page_text["bot_button"])
    html_page = f"""<!doctype html>
<html lang="{norm_lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{ color-scheme: dark; }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0b1220; color: #f3f4f6; }}
    .wrap {{ max-width: 560px; margin: 0 auto; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 24px; box-sizing: border-box; }}
    .card {{ width: 100%; background: #111827; border: 1px solid #1f2937; border-radius: 24px; padding: 24px; box-sizing: border-box; box-shadow: 0 10px 30px rgba(0,0,0,.35); }}
    h1 {{ margin: 0 0 12px; font-size: 28px; line-height: 1.2; }}
    p {{ margin: 0 0 20px; color: #cbd5e1; font-size: 16px; line-height: 1.5; }}
    .actions {{ display: grid; gap: 12px; }}
    .btn {{ display: block; text-align: center; text-decoration: none; padding: 14px 16px; border-radius: 14px; font-weight: 700; }}
    .btn-primary {{ background: #22c55e; color: #04130a; }}
    .btn-secondary {{ background: #1f2937; color: #f3f4f6; }}
    .code {{ margin: 0 0 20px; padding: 16px; border-radius: 16px; background: #0f172a; border: 1px solid #1e293b; }}
    .label {{ font-size: 13px; color: #94a3b8; margin-bottom: 8px; }}
    code {{ display: block; font-size: 15px; font-weight: 700; word-break: break-all; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>{headline}</h1>
      <p>{body}</p>
      {copy_block}
      <div class="actions">
        <a class="btn btn-primary" href="{native_url_attr}">{open_button}</a>
        <a class="btn btn-secondary" href="{android_url}">{android_button}</a>
        <a class="btn btn-secondary" href="{ios_url}">{ios_button}</a>
        <a class="btn btn-secondary" href="{windows_url}">{windows_button}</a>
        <a class="btn btn-secondary" href="{macos_url}">{macos_button}</a>
        <a class="btn btn-secondary" href="{bot_url_attr}">{bot_button}</a>
      </div>
    </div>
  </div>
  <script>
    (function () {{
      const initialNativeUrl = {native_url_js};
      const baseSubscriptionUrl = {subscription_url_js};
      const importName = {import_name_js};
      const androidStoreUrl = {android_url_js};
      const iosStoreUrl = {ios_url_js};
      const primaryButton = document.querySelector('.btn-primary');
      const subscriptionCode = document.getElementById('subscription-link-value');
      const userAgent = navigator.userAgent || '';
      const isAndroid = /Android/i.test(userAgent);
      const isIOS = /iPhone|iPad|iPod/i.test(userAgent);
      let hiddenAt = 0;

      const markHidden = function () {{
        hiddenAt = Date.now();
      }};
      document.addEventListener('visibilitychange', function () {{
        if (document.visibilityState === 'hidden') {{
          markHidden();
        }}
      }});
      window.addEventListener('pagehide', markHidden);
      window.addEventListener('blur', markHidden);

      const getClientId = function () {{
        try {{
          const key = 'inet-subscription-client-id';
          let existing = window.localStorage.getItem(key);
          if (existing) return existing;
          const generated = 'cid-' + Math.random().toString(36).slice(2) + Date.now().toString(36);
          window.localStorage.setItem(key, generated);
          return generated;
        }} catch (error) {{
          return 'cid-' + Date.now().toString(36);
        }}
      }};

      const buildTrackedSubscriptionUrl = function () {{
        if (!baseSubscriptionUrl) return '';
        try {{
          const url = new URL(baseSubscriptionUrl);
          url.searchParams.set('cid', getClientId());
          return url.toString();
        }} catch (error) {{
          return baseSubscriptionUrl;
        }}
      }};

      const buildNativeUrl = function () {{
        const trackedSubscriptionUrl = buildTrackedSubscriptionUrl();
        if (!trackedSubscriptionUrl) return initialNativeUrl || '';
        return 'hiddify://import/' + encodeURIComponent(trackedSubscriptionUrl) + '#' + encodeURIComponent(importName || 'Subscription');
      }};

      const currentNativeUrl = function () {{
        return buildNativeUrl() || initialNativeUrl || '';
      }};

      const currentAndroidIntentUrl = function () {{
        const nativeUrl = currentNativeUrl();
        if (!nativeUrl || !isAndroid) return '';
        const packageId = {json.dumps(_detect_android_app_package())};
        if (!packageId) return '';
        try {{
          const parsed = new URL(nativeUrl);
          const path = (parsed.host ? '//' + parsed.host : '') + (parsed.pathname || '');
          const query = parsed.search || '';
          const hash = parsed.hash || '';
          return 'intent:' + path + query + hash + '#Intent;scheme=' + parsed.protocol.replace(':', '') + ';package=' + packageId + ';end';
        }} catch (error) {{
          return '';
        }}
      }};

      const launchByAnchor = function (url) {{
        if (!url) return;
        const link = document.createElement('a');
        link.href = url;
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
        window.setTimeout(function () {{
          link.remove();
        }}, 250);
      }};

      const openStoreIfNeeded = function () {{
        if (Date.now() - hiddenAt < 1200) {{
          return;
        }}
        const storeUrl = isAndroid ? androidStoreUrl : (isIOS ? iosStoreUrl : '');
        if (storeUrl) {{
          window.location.href = storeUrl;
        }}
      }};

      const tryOpen = function () {{
        const nativeUrl = currentNativeUrl();
        if (!nativeUrl) return;
        if (primaryButton) {{
          primaryButton.href = nativeUrl;
        }}
        const androidIntentUrl = currentAndroidIntentUrl();
        if (isAndroid && androidIntentUrl) {{
          launchByAnchor(androidIntentUrl);
          window.setTimeout(function () {{
            if (Date.now() - hiddenAt < 1200) {{
              return;
            }}
            launchByAnchor(nativeUrl);
          }}, 250);
          window.setTimeout(openStoreIfNeeded, 1800);
          return;
        }}

        launchByAnchor(nativeUrl);
        window.setTimeout(function () {{
          if (Date.now() - hiddenAt < 1200) {{
            return;
          }}
          window.location.href = nativeUrl;
        }}, 180);
        window.setTimeout(openStoreIfNeeded, 1800);
      }};

      if (subscriptionCode) {{
        subscriptionCode.textContent = buildTrackedSubscriptionUrl() || subscriptionCode.textContent || '';
      }}
      if (primaryButton) {{
        primaryButton.href = currentNativeUrl() || primaryButton.href;
      }}
      window.setTimeout(tryOpen, 80);
      primaryButton?.addEventListener('click', function (event) {{
        event.preventDefault();
        tryOpen();
      }});
    }})();
  </script>
</body>
</html>"""
    response = HTMLResponse(content=html_page)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "service": settings.APP_NAME}


@app.post("/auth/telegram")
def auth_telegram(payload: TelegramAuthIn) -> Dict[str, Any]:
    existing = get_user_by_telegram_id(payload.telegram_id)
    user = upsert_telegram_user(payload.model_dump())
    return _issue_auth_payload(user, is_new=existing is None)


@app.post("/auth/code/issue")
def auth_code_issue(request: Request, payload: IssueCodeIn, _: bool = Depends(require_code_issuer)) -> Dict[str, Any]:
    existing = get_user_by_telegram_id(payload.telegram_id)
    user = upsert_telegram_user(payload.model_dump())
    refresh_subscription_statuses(int(user["id"]))
    fresh_user = get_user_by_id(int(user["id"])) or user
    issued = issue_auth_code(
        int(fresh_user["id"]),
        ttl_minutes=settings.AUTH_CODE_TTL_MINUTES,
        meta={
            "telegram_id": payload.telegram_id,
            "language": payload.language,
        },
    )
    code = str(issued["code"])
    deep_link = _build_open_app_bridge_url(
        request,
        code=code,
        lang=fresh_user.get("language") or payload.language or "ru",
    )
    return {
        "ok": True,
        "code": code,
        "deep_link": deep_link,
        "expires_at": issued["expires_at"].isoformat(),
        "user": fresh_user,
        "is_new": existing is None,
    }


@app.post("/auth/code")
def auth_code(payload: CodeAuthIn) -> Dict[str, Any]:
    normalized_code = (payload.code or "").strip()
    if settings.AUTH_ALLOW_DEV_CODE and normalized_code == settings.AUTH_DEV_LOGIN_CODE:
        user_payload = _fallback_code_user_payload(payload)
        existing = get_user_by_telegram_id(int(user_payload["telegram_id"]))
        user = upsert_telegram_user(user_payload)
        return _issue_auth_payload(user, is_new=existing is None)

    user = consume_auth_code(normalized_code)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired code")

    requested_language = "en" if payload.language == "en" else "ru"
    if user.get("language") != requested_language:
        user = set_user_language(int(user["id"]), requested_language)
    return _issue_auth_payload(user, is_new=False)


@app.post("/auth/refresh")
def auth_refresh(
    payload: RefreshIn,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict[str, Any]:
    raw_token = (payload.refresh_token or "").strip()
    if not raw_token and credentials and credentials.credentials:
        raw_token = credentials.credentials
    if not raw_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    decoded = _decode_token(raw_token, expected_type="refresh")
    user_id = int(decoded["sub"])
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return _issue_auth_payload(user, is_new=False)


@app.get("/auth/me")
def auth_me(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    view = get_user_subscription_view(user["id"])
    return {"ok": True, "user": user, **view, "language": user.get("language") or "ru"}


@app.post("/auth/logout")
def auth_logout(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    return {"ok": True, "logged_out": True, "user_id": user["id"]}


@app.patch("/users/me/language")
def patch_language(payload: LanguageIn, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    updated = set_user_language(user["id"], payload.language)
    return {"ok": True, "user": updated}


@app.get("/app/config")
def app_config() -> Dict[str, Any]:
    return {
        "app_name": settings.APP_NAME,
        "support_url": settings.SUPPORT_TELEGRAM_URL,
        "bot_url": _bot_public_url(),
        "maintenance_mode": settings.VPN_MAINTENANCE_MODE,
        "payments_enabled": settings.PAYMENTS_ENABLED,
        "android_app_url": settings.ANDROID_APP_URL,
        "ios_app_url": settings.IOS_APP_URL,
        "windows_app_url": getattr(settings, "WINDOWS_APP_URL", ""),
        "macos_app_url": getattr(settings, "MACOS_APP_URL", ""),
        "device_limit_default": settings.VPN_DEFAULT_DEVICE_LIMIT,
        "feature_flags": {
            "auth_refresh": True,
            "auth_logout": True,
            "maintenance_mode": settings.VPN_MAINTENANCE_MODE,
            "payments_enabled": settings.PAYMENTS_ENABLED,
            "new_activations_enabled": settings.VPN_NEW_ACTIVATIONS_ENABLED,
            "settings_editable": True,
        },
    }


@app.get("/plans")
def plans() -> Dict[str, Any]:
    sync_plans_from_env()
    return {"ok": True, "items": get_active_plans()}


@app.get("/subscriptions/me")
def subscription_me(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    with psycopg.connect(settings.DATABASE_URL, row_factory=dict_row) as conn:
        view = _get_user_subscription_view_with_conn(conn, user["id"])
    if view.get("is_active") and view.get("subscription"):
        subscription_token = view.get("subscription_token") or ensure_user_subscription_token(int(user["id"]))
        subscription_url = _subscription_public_url_from_base(settings.BACKEND_BASE_URL, subscription_token)
    else:
        subscription_token = None
        subscription_url = None
    return {"ok": True, **view, "subscription_token": subscription_token, "subscription_url": subscription_url}


@app.get("/devices")
def devices(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    with psycopg.connect(settings.DATABASE_URL, row_factory=dict_row) as conn:
        view = _get_user_subscription_view_with_conn(conn, user["id"])
    return {"ok": True, "items": view["devices"], "devices_used": view["devices_used"], "device_limit": view["device_limit"]}


@app.post("/devices/register")
def devices_register(payload: DeviceRegisterIn, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    try:
        item = register_device(user["id"], payload.platform, payload.device_name, payload.device_fingerprint)
        return {"ok": True, "device": item}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/devices/{device_id}")
def devices_delete(device_id: int, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    item = delete_device(user["id"], device_id)
    if not item:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"ok": True, "device": item}


@app.get("/locations")
def locations() -> Dict[str, Any]:
    return {"ok": True, "items": _cached_locations_payload()}


@app.get("/locations/status")
def locations_status() -> Dict[str, Any]:
    items = _cached_locations_payload()
    return {"ok": True, "items": [{"code": row["code"], "status": row["status"], "is_active": row["is_active"]} for row in items]}


@app.get("/vpn/config/{location_code}")
def vpn_config(location_code: str, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    try:
        config = get_vpn_config_for_user(user["id"], location_code)
        return {"ok": True, "config": config}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/support/faq")
def support_faq(lang: str = Query(default="ru")) -> Dict[str, Any]:
    norm = "en" if lang == "en" else "ru"
    return {
        "ok": True,
        "lang": norm,
        "support_url": settings.SUPPORT_TELEGRAM_URL,
        "faq": settings.SUPPORT_FAQ_EN if norm == "en" else settings.SUPPORT_FAQ_RU,
    }



def _create_yookassa_payment(local_payment_id: str, amount_rub: float, description: str) -> Dict[str, Any]:
    response = requests.post(
        "https://api.yookassa.ru/v3/payments",
        headers={"Idempotence-Key": str(uuid4())},
        auth=(settings.YOOKASSA_SHOP_ID, settings.YOOKASSA_SECRET_KEY),
        json={
            "amount": {"value": f"{float(amount_rub):.2f}", "currency": "RUB"},
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": settings.YOOKASSA_RETURN_URL},
            "description": description,
            "metadata": {"local_payment_id": local_payment_id, "app_name": settings.APP_NAME},
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


@app.post("/payments/create")
def payments_create(payload: PaymentCreateIn, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if settings.VPN_MAINTENANCE_MODE:
        raise HTTPException(status_code=503, detail="Maintenance mode is enabled")
    if user["status"] == "blocked":
        raise HTTPException(status_code=403, detail="Blocked user cannot create payment")
    plan = get_plan_by_code(payload.plan_code)
    if not plan or not plan["is_active"]:
        raise HTTPException(status_code=404, detail="Plan not found or inactive")
    payment = create_payment_record(
        user_id=user["id"],
        plan_id=plan["id"],
        provider=settings.PAYMENTS_PROVIDER,
        method=payload.method,
        amount=float(plan["price_rub"]),
        currency="RUB",
        status="disabled" if not settings.PAYMENTS_ENABLED else "created",
    )
    if not settings.PAYMENTS_ENABLED:
        return {
            "ok": True,
            "payments_enabled": False,
            "message": "Payment module is ready, but PAYMENTS_ENABLED=false now.",
            "payment": payment,
            "plan": plan,
        }
    if settings.PAYMENTS_PROVIDER == "yookassa":
        if not settings.YOOKASSA_SHOP_ID or not settings.YOOKASSA_SECRET_KEY:
            raise HTTPException(status_code=500, detail="YooKassa credentials are missing")
        try:
            remote = _create_yookassa_payment(payment["id"], float(plan["price_rub"]), f"{settings.APP_NAME} {plan['name_ru']}")
            payment = update_payment(
                payment["id"],
                external_payment_id=remote.get("id"),
                checkout_url=((remote.get("confirmation") or {}).get("confirmation_url")),
                status=remote.get("status", "pending"),
            )
        except requests.RequestException as exc:
            update_payment(payment["id"], status="error")
            raise HTTPException(status_code=502, detail=f"YooKassa create payment failed: {exc}") from exc
    return {"ok": True, "payments_enabled": True, "payment": payment, "plan": plan}


@app.get("/payments/{payment_id}")
def payments_get(payment_id: str, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    payment = get_payment_for_user(payment_id, user["id"])
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    return {"ok": True, "payment": payment}


@app.post("/payments/webhook/yookassa")
def payments_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    obj = payload.get("object") or {}
    remote_payment_id = obj.get("id") or ((obj.get("metadata") or {}).get("local_payment_id"))
    if not remote_payment_id:
        return {"ok": True, "ignored": True}
    payment = get_payment_by_internal_or_external(remote_payment_id)
    if not payment:
        return {"ok": True, "ignored": True}
    status_value = obj.get("status") or payload.get("event") or payment["status"]
    if status_value in {"succeeded", "paid"}:
        activate_payment_and_extend_subscription(payment["id"])
    elif status_value in {"canceled", "cancelled"}:
        update_payment(payment["id"], status="cancelled")
        enqueue_notification(
            user_id=payment['user_id'],
            event_type='payment_failed',
            unique_key=f'payment_failed:{payment["id"]}',
            payload={'payment_id': payment['id']},
        )
    else:
        update_payment(payment["id"], status=status_value)
    return {"ok": True}


@app.get("/api/infra/admin/vpn/users")
def admin_users(
    search: str = Query(default=""),
    query_text: str = Query(default="", alias="query"),
    status_filter: str = Query(default="all", alias="status"),
    filter_text: str = Query(default="", alias="filter"),
    admin_name: str = Depends(require_admin),
) -> Dict[str, Any]:
    _ = admin_name
    effective_search = query_text or search
    effective_status = filter_text or status_filter or "all"
    data = list_admin_users(search=effective_search, status_filter=effective_status)
    return {"ok": True, **data}


@app.post("/api/infra/admin/vpn/users")
def admin_users_create(payload: AdminUserUpsertIn, admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    try:
        item = admin_create_or_update_user(payload.model_dump(exclude_none=True), admin_name)
        return {"ok": True, "item": item}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/infra/admin/vpn/users/{telegram_id}")
def admin_user_patch(telegram_id: int, payload: AdminUserPatchIn, admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    data = payload.model_dump(exclude_unset=True)
    if "device_limit_override" not in data:
        raise HTTPException(status_code=400, detail="No changes provided")
    try:
        item = set_user_device_limit_override_by_telegram(telegram_id, data.get("device_limit_override"), admin_name)
        return {"ok": True, "item": item}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.patch("/api/infra/admin/vpn/users/{telegram_id}/block")
def admin_user_block(telegram_id: int, admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    try:
        user = set_user_status_by_telegram(telegram_id, "blocked", admin_name, "User blocked from VPN admin")
        return {"ok": True, "user": user}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.patch("/api/infra/admin/vpn/users/{telegram_id}/unblock")
def admin_user_unblock(telegram_id: int, admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    try:
        user = set_user_status_by_telegram(telegram_id, "active", admin_name, "User unblocked from VPN admin")
        return {"ok": True, "user": user}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/infra/admin/vpn/users/{telegram_id}/extend")
def admin_user_extend(telegram_id: int, payload: ExtendIn, admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    try:
        item = extend_user_subscription_by_telegram(telegram_id, payload.normalized_days(), payload.reason, admin_name)
        return {"ok": True, "item": item}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/infra/admin/vpn/users/{telegram_id}/reset-devices")
def admin_user_reset_devices(telegram_id: int, admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    try:
        item = reset_user_devices_by_telegram(telegram_id, admin_name)
        return {"ok": True, "item": item}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/infra/admin/vpn/payments")
def admin_payments(status_filter: str = Query(default="all", alias="status"), admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    _ = admin_name
    return {"ok": True, "items": list_payments(status_filter=status_filter)}


@app.get("/api/infra/admin/vpn/payments/export.csv")
def admin_payments_export(status_filter: str = Query(default="all", alias="status"), admin_name: str = Depends(require_admin)) -> Response:
    _ = admin_name
    content = export_payments_csv(status_filter=status_filter)
    return Response(content=content, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=vpn-payments.csv"})


def _safe_speed_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not (number >= 0):
        return None
    return round(number, 2)


def _safe_speed_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return number


def _location_speed_test_url(row: Dict[str, Any]) -> Optional[str]:
    payload = _compose_vpn_payload_for_location(dict(row))
    candidates = [
        payload.get("speed_test_url"),
        payload.get("speedtest_url"),
        payload.get("speed_url"),
        payload.get("metrics_url"),
    ]
    for value in candidates:
        text = str(value or "").strip()
        if text.lower().startswith(("http://", "https://")):
            return text

    server = str(payload.get("speed_test_host") or payload.get("server") or "").strip()
    if not server or "://" in server:
        return None
    scheme = str(payload.get("speed_test_scheme") or "https").strip() or "https"
    path = str(payload.get("speed_test_path") or "/speed").strip() or "/speed"
    if not path.startswith("/"):
        path = "/" + path
    try:
        port = int(payload.get("speed_test_port") or 0)
    except (TypeError, ValueError):
        port = 0
    base = f"{scheme}://{server}"
    if port > 0 and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        base += f":{port}"
    return base + path


def _extract_speed_metrics(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Speed test response must be a JSON object")

    source = data
    for key in ("data", "result", "speed", "metrics"):
        nested = source.get(key)
        if isinstance(nested, dict):
            source = nested
            break

    download = _safe_speed_float(
        source.get("download_mbps")
        or source.get("downloadMbps")
        or source.get("download")
        or data.get("download_mbps")
        or data.get("downloadMbps")
        or data.get("download")
    )
    upload = _safe_speed_float(
        source.get("upload_mbps")
        or source.get("uploadMbps")
        or source.get("upload")
        or data.get("upload_mbps")
        or data.get("uploadMbps")
        or data.get("upload")
    )
    ping = _safe_speed_int(
        source.get("ping_ms")
        or source.get("pingMs")
        or source.get("ping")
        or data.get("ping_ms")
        or data.get("pingMs")
        or data.get("ping")
    )
    checked_at = (
        source.get("checked_at")
        or source.get("checkedAt")
        or source.get("timestamp")
        or data.get("checked_at")
        or data.get("checkedAt")
        or data.get("timestamp")
    )

    if download is None and upload is None and ping is None:
        raise ValueError("Response has no speed fields")

    if checked_at:
        checked_text = str(checked_at).strip()
        try:
            checked_iso = datetime.fromisoformat(checked_text.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
        except ValueError:
            checked_iso = datetime.now(timezone.utc).isoformat()
    else:
        checked_iso = datetime.now(timezone.utc).isoformat()

    return {
        "download_mbps": download,
        "upload_mbps": upload,
        "ping_ms": ping,
        "speed_checked_at": checked_iso,
    }


def _run_location_speed_test(row: Dict[str, Any]) -> Dict[str, Any]:
    code = str(row.get("code") or "")
    status = str(row.get("status") or "").lower()
    is_active = bool(row.get("is_active"))
    result: Dict[str, Any] = {
        "id": row.get("id"),
        "code": code,
        "name_ru": row.get("name_ru"),
        "status": "skipped",
    }

    if code in {"auto-fastest", "auto-reserve"}:
        result["reason"] = "virtual_location"
        return result
    if not is_active:
        result["reason"] = "inactive"
        return result
    if status != "online":
        result["reason"] = "not_online"
        return result

    payload = _compose_vpn_payload_for_location(dict(row))
    if not payload or not _config_is_complete(payload):
        result["reason"] = "payload_incomplete"
        return result

    url = _location_speed_test_url(row)
    if not url:
        result["reason"] = "speed_test_url_missing"
        result["hint"] = "Set vpn_payload.speed_test_url or speed_test_host/scheme/path."
        return result

    try:
        response = requests.get(url, timeout=12, headers={"Accept": "application/json"})
        response.raise_for_status()
        metrics = _extract_speed_metrics(response.json())
        item = patch_location(int(row.get("id")), metrics)
        result.update({
            "status": "ok",
            "url": url,
            "metrics": {
                "download_mbps": item.get("download_mbps"),
                "upload_mbps": item.get("upload_mbps"),
                "ping_ms": item.get("ping_ms"),
                "speed_checked_at": (
                    item.get("speed_checked_at").astimezone(timezone.utc).isoformat()
                    if isinstance(item.get("speed_checked_at"), datetime)
                    else item.get("speed_checked_at")
                ),
            },
        })
        return result
    except requests.RequestException as exc:
        result.update({"status": "error", "url": url, "reason": str(exc)})
        return result
    except ValueError as exc:
        result.update({"status": "error", "url": url, "reason": str(exc)})
        return result


@app.post("/api/infra/admin/vpn/locations/speed-test")
def admin_locations_speed_test(admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    _ = admin_name
    rows = list_locations(active_only=False)
    results = [_run_location_speed_test(row) for row in rows]
    ok_count = sum(1 for item in results if item.get("status") == "ok")
    error_count = sum(1 for item in results if item.get("status") == "error")
    skipped_count = sum(1 for item in results if item.get("status") == "skipped")
    _invalidate_locations_cache()
    return {
        "ok": True,
        "tested": len(results),
        "updated": ok_count,
        "errors": error_count,
        "skipped": skipped_count,
        "items": results,
    }

@app.post("/api/infra/admin/vpn/locations/refresh-ru-lte")
def admin_refresh_ru_lte(admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    _ = admin_name
    return _run_ru_lte_refresh_safe(source="manual")


@app.post("/api/infra/admin/vpn/locations/refresh-black")
def admin_refresh_black(admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    _ = admin_name
    return _run_black_refresh_safe(source="manual")


@app.get("/api/infra/admin/vpn/locations")
def admin_locations(admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    _ = admin_name
    return {
        "ok": True,
        "items": [serialize_location(row, include_payload=True) for row in list_locations(active_only=False)],
        "ru_lte_refresh": dict(_ru_lte_refresh_state),
        "ru_lte_auto_refresh_enabled": bool(settings.RU_LTE_AUTO_REFRESH_ENABLED),
        "ru_lte_auto_refresh_minutes": max(1, int(settings.RU_LTE_AUTO_REFRESH_MINUTES or 30)),
        "black_refresh": dict(_black_refresh_state),
        "black_auto_refresh_enabled": bool(settings.BLACK_AUTO_REFRESH_ENABLED),
        "black_auto_refresh_minutes": max(1, int(settings.BLACK_AUTO_REFRESH_MINUTES or 30)),
    }


@app.post("/api/infra/admin/vpn/locations")
def admin_locations_create(payload: LocationIn, admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    _ = admin_name
    try:
        item = create_location(payload.model_dump())
        return {"ok": True, "item": serialize_location(item, include_payload=True)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except psycopg.Error as exc:
        detail = str(exc).strip() or "Database error while saving location"
        raise HTTPException(status_code=500, detail=detail) from exc


@app.patch("/api/infra/admin/vpn/locations/{location_id}")
def admin_locations_patch(location_id: int, payload: LocationPatchIn, admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    _ = admin_name
    data = {key: value for key, value in payload.model_dump().items() if value is not None}
    try:
        item = patch_location(location_id, data)
        return {"ok": True, "item": serialize_location(item, include_payload=True)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/infra/admin/vpn/locations/{location_id}")
def admin_locations_delete(location_id: int, admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    _ = admin_name
    try:
        item = delete_location(location_id)
        return {"ok": True, "item": serialize_location(item, include_payload=True)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/infra/admin/vpn/settings")
def admin_settings(admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    _ = admin_name
    sync_plans_from_env()
    return {"ok": True, "settings": settings_snapshot()}


@app.post("/api/infra/admin/vpn/settings")
def admin_settings_save(payload: AdminVpnSettingsIn, admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    _ = admin_name
    save_runtime_settings_payload(payload.model_dump(exclude_none=True))
    return {
        "ok": True,
        "message": "Settings saved to database and applied immediately.",
        "settings": settings_snapshot(),
    }



def _telegram_api_url(method: str) -> str:
    if not settings.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not configured")
    return f"https://api.telegram.org/bot{settings.BOT_TOKEN}/{method}"



def telegram_send_message(telegram_id: int, text: str, reply_markup: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"chat_id": int(telegram_id), "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    response = requests.post(_telegram_api_url("sendMessage"), json=payload, timeout=20)
    response.raise_for_status()
    return response.json()


@app.post("/api/infra/admin/vpn/test-send")
def admin_test_send(payload: TestSendIn, admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    _ = admin_name
    try:
        telegram_send_message(payload.telegram_id, payload.text)
        return {"ok": True}
    except Exception as exc:
        record_bot_error("vpn-admin-test", str(payload.telegram_id), str(exc))
        raise HTTPException(status_code=502, detail=f"Telegram send failed: {exc}") from exc


@app.post("/api/infra/admin/vpn/broadcast")
def admin_broadcast(payload: BroadcastIn, admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    _ = admin_name
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required")
    sent = 0
    failed = 0
    for target in list_broadcast_targets(payload.statuses or ["active"]):
        try:
            telegram_send_message(int(target["telegram_id"]), text)
            sent += 1
        except Exception as exc:
            failed += 1
            record_bot_error("vpn-broadcast", str(target.get("telegram_id")), str(exc))
    return {"ok": True, "sent": sent, "failed": failed, "total": sent + failed}


@app.post("/vpn/client-events")
def vpn_client_events(payload: VpnClientEventIn, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    platform = _diagnostic_text(payload.platform).lower() or "unknown"
    stage = _diagnostic_text(payload.stage).lower() or "runtime"
    status = _diagnostic_text(payload.status).lower()
    location_code = _diagnostic_text(payload.location_code)
    user_label = str(user.get("telegram_id") or user.get("id") or "unknown")
    context_parts = [f"user={user_label}"]
    if location_code:
        context_parts.append(f"location={location_code}")
    if status:
        context_parts.append(f"status={status}")
    message = _diagnostic_text(payload.error_message) or _diagnostic_text(payload.details) or f"Client VPN event: {stage}"
    record_bot_error(f"vpn-client-{platform}-{stage}", " | ".join(context_parts), message)
    return {"ok": True}


@app.get("/api/infra/admin/vpn/errors")
def admin_errors(limit: int = Query(default=50, ge=1, le=500), admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    _ = admin_name
    items = list_bot_errors(limit=limit) + build_location_tun_error_items()
    items.sort(key=lambda item: _diagnostic_text(item.get("created_at")) or "", reverse=True)
    return {"ok": True, "items": items[:limit]}
