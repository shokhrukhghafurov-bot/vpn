from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import html
import json
import secrets
from uuid import uuid4

import jwt
import requests
import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
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
    _config_is_complete,
    _pick_virtual_location,
    get_active_plans,
    get_payment_by_internal_or_external,
    get_payment_for_user,
    get_plan_by_code,
    get_vpn_config_for_user,
    get_user_by_id,
    get_user_by_telegram_id,
    get_user_snapshot_by_telegram,
    get_user_subscription_view,
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


@app.on_event("startup")
def on_startup() -> None:
    bootstrap()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.CORS_ORIGINS == ["*"] else settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


def _build_native_open_app_url(*, code: Optional[str] = None, token: Optional[str] = None, lang: Optional[str] = None) -> str:
    base = settings.OPEN_APP_URL or "inet://login"
    parts = urlsplit(base)
    path = parts.path
    if parts.scheme and parts.scheme not in {"http", "https"} and path == "/":
        path = ""
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if code:
        query["code"] = code
    elif token:
        query["token"] = token
    if lang:
        query["lang"] = lang
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), parts.fragment))


def _build_open_app_bridge_url(request: Request, *, code: Optional[str] = None, token: Optional[str] = None, lang: Optional[str] = None) -> str:
    base = (settings.OPEN_APP_BRIDGE_URL or "").strip() or str(request.url_for("open_app_bridge"))
    parts = urlsplit(base)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if code:
        query["code"] = code
    elif token:
        query["token"] = token
    if lang:
        query["lang"] = lang
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


@app.get("/open-app", response_class=HTMLResponse, name="open_app_bridge")
def open_app_bridge(
    request: Request,
    code: Optional[str] = Query(default=None),
    token: Optional[str] = Query(default=None),
    lang: str = Query(default="ru"),
) -> HTMLResponse:
    norm_lang = "en" if lang == "en" else "ru"
    native_url = _build_native_open_app_url(code=code, token=token, lang=norm_lang)
    bot_url = _bot_public_url()
    page_text = {
        "ru": {
            "title": "Открываем INET",
            "headline": "Открываем приложение…",
            "body": "Приложение должно открыться автоматически. Если этого не произошло, нажмите кнопку ниже.",
            "open_button": "Открыть приложение",
            "android_button": "Скачать Android",
            "ios_button": "Скачать iPhone / iPad",
            "bot_button": "Вернуться в бота",
            "code_label": "Код для входа",
        },
        "en": {
            "title": "Opening INET",
            "headline": "Opening the app…",
            "body": "The app should open automatically. If it does not, use the button below.",
            "open_button": "Open app",
            "android_button": "Download Android",
            "ios_button": "Download iPhone / iPad",
            "bot_button": "Back to bot",
            "code_label": "Login code",
        },
    }[norm_lang]
    code_block = ""
    if code:
        code_block = f'<div class="code"><div class="label">{html.escape(page_text["code_label"])}</div><code>{html.escape(code)}</code></div>'
    native_url_attr = html.escape(native_url, quote=True)
    native_url_js = json.dumps(native_url)
    android_url = html.escape(settings.ANDROID_APP_URL, quote=True)
    ios_url = html.escape(settings.IOS_APP_URL, quote=True)
    bot_url_attr = html.escape(bot_url, quote=True)
    title = html.escape(page_text["title"])
    headline = html.escape(page_text["headline"])
    body = html.escape(page_text["body"])
    open_button = html.escape(page_text["open_button"])
    android_button = html.escape(page_text["android_button"])
    ios_button = html.escape(page_text["ios_button"])
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
    code {{ display: block; font-size: 18px; font-weight: 700; word-break: break-all; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>{headline}</h1>
      <p>{body}</p>
      {code_block}
      <div class="actions">
        <a class="btn btn-primary" href="{native_url_attr}">{open_button}</a>
        <a class="btn btn-secondary" href="{android_url}">{android_button}</a>
        <a class="btn btn-secondary" href="{ios_url}">{ios_button}</a>
        <a class="btn btn-secondary" href="{bot_url_attr}">{bot_button}</a>
      </div>
    </div>
  </div>
  <script>
    window.setTimeout(function () {{
      window.location.href = {native_url_js};
    }}, 120);
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
    view = get_user_subscription_view(user["id"])
    return {"ok": True, **view}


@app.get("/devices")
def devices(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    view = get_user_subscription_view(user["id"])
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
    return {"ok": True, "items": [serialize_location(row) for row in list_locations(active_only=True)]}


@app.get("/locations/status")
def locations_status() -> Dict[str, Any]:
    rows = list_locations(active_only=True)
    return {"ok": True, "items": [{"code": row["code"], "status": row["status"], "is_active": row["is_active"]} for row in rows]}


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


@app.get("/api/infra/admin/vpn/locations")
def admin_locations(admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    _ = admin_name
    return {"ok": True, "items": [serialize_location(row, include_payload=True) for row in list_locations(active_only=False)]}


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
