import csv
import io
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from config import settings


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL UNIQUE,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    language TEXT NOT NULL DEFAULT 'ru',
    status TEXT NOT NULL DEFAULT 'active',
    device_limit_override INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);

CREATE TABLE IF NOT EXISTS plans (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name_ru TEXT NOT NULL,
    name_en TEXT NOT NULL,
    price_rub NUMERIC(10,2) NOT NULL,
    duration_days INTEGER NOT NULL,
    device_limit INTEGER NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    source_env_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_id INTEGER NOT NULL REFERENCES plans(id),
    starts_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);

CREATE TABLE IF NOT EXISTS devices (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    device_name TEXT,
    device_fingerprint TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, device_fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_devices_user_id ON devices(user_id);

CREATE TABLE IF NOT EXISTS locations (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name_ru TEXT NOT NULL,
    name_en TEXT NOT NULL,
    country_code TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_recommended BOOLEAN NOT NULL DEFAULT FALSE,
    is_reserve BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'online',
    sort_order INTEGER NOT NULL DEFAULT 100,
    vpn_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    location_source TEXT NOT NULL DEFAULT 'catalog',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payments (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_id INTEGER NOT NULL REFERENCES plans(id),
    provider TEXT NOT NULL,
    method TEXT,
    amount NUMERIC(10,2) NOT NULL,
    currency TEXT NOT NULL DEFAULT 'RUB',
    status TEXT NOT NULL DEFAULT 'created',
    external_payment_id TEXT UNIQUE,
    checkout_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    paid_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);

CREATE TABLE IF NOT EXISTS auth_codes (
    code TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    meta JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_auth_codes_user_id ON auth_codes(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_codes_expires_at ON auth_codes(expires_at);

CREATE TABLE IF NOT EXISTS admin_notes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    admin_name TEXT NOT NULL,
    note TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS manual_extensions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    days_added INTEGER NOT NULL,
    reason TEXT,
    admin_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bot_notifications (
    id BIGSERIAL PRIMARY KEY,
    unique_key TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_bot_notifications_unsent ON bot_notifications(sent_at, created_at);

CREATE TABLE IF NOT EXISTS bot_error_log (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    context TEXT,
    error_message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

MIGRATION_SQL = [
    # users
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name TEXT",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS language TEXT DEFAULT 'ru'",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active'",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS device_limit_override INTEGER",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",

    # plans
    "ALTER TABLE plans ADD COLUMN IF NOT EXISTS device_limit INTEGER DEFAULT 2",
    "ALTER TABLE plans ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
    "ALTER TABLE plans ADD COLUMN IF NOT EXISTS source_env_key TEXT",
    "ALTER TABLE plans ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
    "ALTER TABLE plans ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",

    # subscriptions
    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active'",
    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",

    # devices
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS device_name TEXT",
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ DEFAULT NOW()",
    "ALTER TABLE devices ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",

    # locations
    "ALTER TABLE locations ADD COLUMN IF NOT EXISTS country_code TEXT",
    "ALTER TABLE locations ADD COLUMN IF NOT EXISTS is_recommended BOOLEAN DEFAULT FALSE",
    "ALTER TABLE locations ADD COLUMN IF NOT EXISTS is_reserve BOOLEAN DEFAULT FALSE",
    "ALTER TABLE locations ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'online'",
    "ALTER TABLE locations ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 100",
    "ALTER TABLE locations ADD COLUMN IF NOT EXISTS vpn_payload JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE locations ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE",
    "ALTER TABLE locations ADD COLUMN IF NOT EXISTS location_source TEXT DEFAULT 'catalog'",
    "ALTER TABLE locations ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
    "ALTER TABLE locations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",

    # payments
    "ALTER TABLE payments ADD COLUMN IF NOT EXISTS method TEXT",
    "ALTER TABLE payments ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'RUB'",
    "ALTER TABLE payments ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'created'",
    "ALTER TABLE payments ADD COLUMN IF NOT EXISTS external_payment_id TEXT",
    "ALTER TABLE payments ADD COLUMN IF NOT EXISTS checkout_url TEXT",
    "ALTER TABLE payments ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
    "ALTER TABLE payments ADD COLUMN IF NOT EXISTS paid_at TIMESTAMPTZ",

    # notifications/errors
    "ALTER TABLE bot_notifications ADD COLUMN IF NOT EXISTS payload JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE bot_notifications ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
    "ALTER TABLE bot_notifications ADD COLUMN IF NOT EXISTS sent_at TIMESTAMPTZ",
    "ALTER TABLE bot_error_log ADD COLUMN IF NOT EXISTS context TEXT",
    "ALTER TABLE bot_error_log ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",

    # indexes compatible with old databases
    "CREATE INDEX IF NOT EXISTS idx_users_status ON users(status)",
    "CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status)",
    "CREATE INDEX IF NOT EXISTS idx_devices_user_id ON devices(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)",
    "CREATE INDEX IF NOT EXISTS idx_bot_notifications_unsent ON bot_notifications(sent_at, created_at)",
]

POST_MIGRATION_SQL = [
    "UPDATE users SET language = 'ru' WHERE language IS NULL OR language = ''",
    "UPDATE users SET status = 'active' WHERE status IS NULL OR status = ''",
    "UPDATE users SET device_limit_override = NULL WHERE device_limit_override IS NOT NULL AND device_limit_override <= 0",
    f"UPDATE plans SET device_limit = {int(settings.VPN_DEFAULT_DEVICE_LIMIT)} WHERE device_limit IS NULL OR device_limit <= 0",
    "UPDATE plans SET is_active = TRUE WHERE is_active IS NULL",
    "UPDATE plans SET source_env_key = code WHERE source_env_key IS NULL OR source_env_key = ''",
    "UPDATE subscriptions SET status = 'active' WHERE status IS NULL OR status = ''",
    "UPDATE locations SET status = 'online' WHERE status IS NULL OR status = ''",
    "UPDATE locations SET sort_order = 100 WHERE sort_order IS NULL",
    "UPDATE locations SET is_recommended = FALSE WHERE is_recommended IS NULL",
    "UPDATE locations SET is_reserve = FALSE WHERE is_reserve IS NULL",
    "UPDATE locations SET vpn_payload = '{}'::jsonb WHERE vpn_payload IS NULL",
    "UPDATE locations SET is_deleted = FALSE WHERE is_deleted IS NULL",
    "UPDATE locations SET location_source = 'catalog' WHERE location_source IS NULL OR location_source = ''",
    "UPDATE payments SET currency = 'RUB' WHERE currency IS NULL OR currency = ''",
    "UPDATE payments SET status = 'created' WHERE status IS NULL OR status = ''",
    "UPDATE bot_notifications SET payload = '{}'::jsonb WHERE payload IS NULL",
]

SERIAL_ID_TABLES = (
    ("users", "id"),
    ("plans", "id"),
    ("subscriptions", "id"),
    ("devices", "id"),
    ("locations", "id"),
    ("admin_notes", "id"),
    ("manual_extensions", "id"),
    ("bot_notifications", "id"),
    ("bot_error_log", "id"),
)



def _run_schema_migrations(cur: psycopg.Cursor) -> None:
    for statement in MIGRATION_SQL:
        cur.execute(statement)
    for statement in POST_MIGRATION_SQL:
        cur.execute(statement)


def _resync_serial_sequence(cur: psycopg.Cursor, table_name: str, column_name: str = "id") -> None:
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = %s
              AND column_name = %s
        ) AS column_exists
        """,
        (table_name, column_name),
    )
    column_row = cur.fetchone() or {}
    if not column_row.get("column_exists"):
        return

    cur.execute("SELECT pg_get_serial_sequence(%s, %s) AS sequence_name", (table_name, column_name))
    row = cur.fetchone()
    if not row:
        return
    sequence_name = row.get("sequence_name")
    if not sequence_name:
        return
    cur.execute(
        sql.SQL("SELECT COALESCE(MAX({column}), 0) AS max_id FROM {table}").format(
            column=sql.Identifier(column_name),
            table=sql.Identifier(table_name),
        )
    )
    max_id_row = cur.fetchone()
    max_id = int((max_id_row or {}).get("max_id") or 0)
    next_value = max(1, max_id + 1)
    cur.execute("SELECT setval(%s, %s, false)", (sequence_name, next_value))


def _resync_serial_sequences(cur: psycopg.Cursor) -> None:
    for table_name, column_name in SERIAL_ID_TABLES:
        _resync_serial_sequence(cur, table_name, column_name)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def db() -> psycopg.Connection:
    return psycopg.connect(settings.DATABASE_URL, row_factory=dict_row)


def bootstrap() -> None:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            _run_schema_migrations(cur)
            _resync_serial_sequences(cur)
        conn.commit()
    sync_plans_from_env()
    sync_locations_catalog()


def sync_plans_from_env() -> None:
    with db() as conn:
        with conn.cursor() as cur:
            for plan in settings.plan_definitions():
                cur.execute(
                    """
                    INSERT INTO plans (code, name_ru, name_en, price_rub, duration_days, device_limit, is_active, source_env_key)
                    VALUES (%(code)s, %(name_ru)s, %(name_en)s, %(price_rub)s, %(duration_days)s, %(device_limit)s, %(is_active)s, %(source_env_key)s)
                    ON CONFLICT (code) DO UPDATE SET
                        name_ru = EXCLUDED.name_ru,
                        name_en = EXCLUDED.name_en,
                        price_rub = EXCLUDED.price_rub,
                        duration_days = EXCLUDED.duration_days,
                        device_limit = EXCLUDED.device_limit,
                        is_active = EXCLUDED.is_active,
                        source_env_key = EXCLUDED.source_env_key,
                        updated_at = NOW()
                    """,
                    plan,
                )
        conn.commit()


def _parse_locations_json(raw_json: str) -> List[Dict[str, Any]]:
    try:
        raw_locations = json.loads(raw_json or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(raw_locations, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw_locations, start=1):
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        name_ru = str(item.get("name_ru") or "").strip()
        name_en = str(item.get("name_en") or name_ru).strip()
        if not code or not name_ru or not name_en:
            continue
        country_code = item.get("country_code")
        if country_code is not None:
            country_code = str(country_code).strip().upper() or None
        normalized.append(
            {
                "code": code,
                "name_ru": name_ru,
                "name_en": name_en,
                "country_code": country_code,
                "is_active": bool(item.get("is_active", True)),
                "is_recommended": bool(item.get("is_recommended", False)),
                "is_reserve": bool(item.get("is_reserve", False)),
                "status": str(item.get("status") or "online").strip() or "online",
                "sort_order": int(item.get("sort_order") or idx * 10),
                "vpn_payload": item.get("vpn_payload") if isinstance(item.get("vpn_payload"), dict) else {},
                "is_deleted": bool(item.get("is_deleted", False)),
                "location_source": str(item.get("location_source") or "catalog").strip() or "catalog",
            }
        )
    return normalized



def _load_default_locations() -> List[Dict[str, Any]]:
    builtin_locations = _parse_locations_json(settings.DEFAULT_LOCATIONS_JSON)
    if settings.DEFAULT_LOCATIONS_ENV_OVERRIDE_ENABLED:
        env_locations = _parse_locations_json(settings.DEFAULT_LOCATIONS_ENV_JSON)
        if env_locations:
            return env_locations
    return builtin_locations


def _parse_json_object_if_possible(raw: Any) -> Optional[Dict[str, Any]]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        candidate = raw.strip()
        if not candidate:
            return None
        try:
            value = json.loads(candidate)
        except Exception:
            return None
        if isinstance(value, dict):
            return value
    return None


def _extract_dns_servers_from_xray(payload: Dict[str, Any]) -> List[str]:
    dns = payload.get("dns")
    if not isinstance(dns, dict):
        return []
    servers = dns.get("servers")
    if not isinstance(servers, list):
        return []
    result: List[str] = []
    for item in servers:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
        elif isinstance(item, dict):
            address = str(item.get("address") or "").strip()
            if address:
                result.append(address)
    return result


def _convert_raw_xray_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    outbounds = payload.get("outbounds")
    if not isinstance(outbounds, list):
        return {}

    proxy = None
    for outbound in outbounds:
        if not isinstance(outbound, dict):
            continue
        protocol = str(outbound.get("protocol") or "").strip().lower()
        if protocol == "vless":
            proxy = outbound
            if str(outbound.get("tag") or "").strip().lower() == "proxy":
                break
    if not isinstance(proxy, dict):
        return {}

    settings_payload = proxy.get("settings")
    stream_settings = proxy.get("streamSettings") if isinstance(proxy.get("streamSettings"), dict) else {}
    vnext = settings_payload.get("vnext") if isinstance(settings_payload, dict) else None
    if not isinstance(vnext, list) or not vnext:
        return {}
    upstream = vnext[0] if isinstance(vnext[0], dict) else {}
    users = upstream.get("users") if isinstance(upstream, dict) else None
    if not isinstance(users, list) or not users:
        return {}
    user = users[0] if isinstance(users[0], dict) else {}

    grpc_settings = stream_settings.get("grpcSettings") if isinstance(stream_settings.get("grpcSettings"), dict) else {}
    ws_settings = stream_settings.get("wsSettings") if isinstance(stream_settings.get("wsSettings"), dict) else {}
    reality_settings = stream_settings.get("realitySettings") if isinstance(stream_settings.get("realitySettings"), dict) else {}
    tls_settings = stream_settings.get("tlsSettings") if isinstance(stream_settings.get("tlsSettings"), dict) else {}

    security = str(stream_settings.get("security") or proxy.get("security") or "reality").strip() or "reality"
    server_name = str(
        reality_settings.get("serverName")
        or tls_settings.get("serverName")
        or proxy.get("sni")
        or ""
    ).strip()

    converted: Dict[str, Any] = {
        "protocol": "vless",
        "engine": "sing-box",
        "server": str(upstream.get("address") or "").strip(),
        "port": upstream.get("port"),
        "uuid": str(user.get("id") or "").strip(),
        "transport": str(stream_settings.get("network") or proxy.get("network") or "tcp").strip() or "tcp",
        "network": str(stream_settings.get("network") or proxy.get("network") or "tcp").strip() or "tcp",
        "security": security,
        "flow": str(user.get("flow") or "").strip() or None,
        "sni": server_name or None,
        "server_name": server_name or None,
        "service_name": str(grpc_settings.get("serviceName") or "").strip() or None,
        "public_key": str(reality_settings.get("publicKey") or "").strip() or None,
        "short_id": str(reality_settings.get("shortId") or "").strip() or None,
        "fingerprint": str(reality_settings.get("fingerprint") or tls_settings.get("fingerprint") or "").strip() or None,
        "allow_insecure": bool(tls_settings.get("allowInsecure") or proxy.get("allowInsecure") or False),
        "host": None,
        "path": None,
        "packet_encoding": "xudp",
        "domain_resolver": "dns-remote",
        "connect_mode": "tun",
        "full_tunnel": True,
        "raw_xray_config": json.dumps(payload, ensure_ascii=False),
        "rawXrayConfig": json.dumps(payload, ensure_ascii=False),
    }

    if converted["transport"] in {"ws", "websocket"}:
        converted["host"] = str(ws_settings.get("headers", {}).get("Host") or "").strip() or None
        converted["path"] = str(ws_settings.get("path") or "/").strip() or "/"

    dns_servers = _extract_dns_servers_from_xray(payload)
    if dns_servers:
        converted["dns_servers"] = dns_servers
        converted["dnsServers"] = dns_servers

    alpn = tls_settings.get("alpn")
    if isinstance(alpn, list):
        normalized_alpn = [str(item).strip() for item in alpn if str(item).strip()]
        if normalized_alpn:
            converted["alpn"] = normalized_alpn

    return {key: value for key, value in converted.items() if value is not None and value != ""}


def _apply_admin_mobile_defaults(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(payload or {})
    if not normalized:
        return {}

    raw_xray = normalized.get("raw_xray_config") or normalized.get("rawXrayConfig")
    raw_xray_payload = _parse_json_object_if_possible(raw_xray)
    if raw_xray_payload:
        converted = _convert_raw_xray_payload(raw_xray_payload)
        for key, value in converted.items():
            if normalized.get(key) in (None, "", [], {}):
                normalized[key] = value

    engine = str(normalized.get("engine") or "").strip().lower()
    if engine in {"", "xray", "xray-core"}:
        normalized["engine"] = "sing-box"

    normalized.setdefault("protocol", "vless")
    normalized.setdefault("transport", normalized.get("network") or "tcp")
    normalized.setdefault("network", normalized.get("transport") or "tcp")
    normalized.setdefault("security", "reality")
    normalized.setdefault("mtu", 1400)
    normalized.setdefault("domain_resolver", "dns-remote")
    normalized.setdefault("packet_encoding", "xudp")
    normalized.setdefault("connect_mode", "tun")
    normalized.setdefault("full_tunnel", True)

    dns_servers = normalized.get("dns_servers") or normalized.get("dnsServers")
    if not dns_servers:
        normalized["dns_servers"] = ["1.1.1.1", "8.8.8.8"]
        normalized["dnsServers"] = ["1.1.1.1", "8.8.8.8"]
    return normalized


def _normalize_vpn_payload_keys(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(payload or {})
    if not normalized:
        return {}
    if "server_port" in normalized and "port" not in normalized:
        normalized["port"] = normalized.get("server_port")
    if "id" in normalized and "uuid" not in normalized:
        normalized["uuid"] = normalized.get("id")
    if "network" in normalized and "transport" not in normalized:
        normalized["transport"] = normalized.get("network")
    if "transport" in normalized and "network" not in normalized:
        normalized["network"] = normalized.get("transport")
    if "server_name" in normalized and "sni" not in normalized:
        normalized["sni"] = normalized.get("server_name")
    if "sni" in normalized and "server_name" not in normalized:
        normalized["server_name"] = normalized.get("sni")
    if "serviceName" in normalized and "service_name" not in normalized:
        normalized["service_name"] = normalized.get("serviceName")
    if "service_name" in normalized and "serviceName" not in normalized:
        normalized["serviceName"] = normalized.get("service_name")
    if "publicKey" in normalized and "public_key" not in normalized:
        normalized["public_key"] = normalized.get("publicKey")
    if "public_key" in normalized and "publicKey" not in normalized:
        normalized["publicKey"] = normalized.get("public_key")
    if "shortId" in normalized and "short_id" not in normalized:
        normalized["short_id"] = normalized.get("shortId")
    if "short_id" in normalized and "shortId" not in normalized:
        normalized["shortId"] = normalized.get("short_id")
    if "dnsServers" in normalized and "dns_servers" not in normalized:
        normalized["dns_servers"] = normalized.get("dnsServers")
    if "dns_servers" in normalized and "dnsServers" not in normalized:
        normalized["dnsServers"] = normalized.get("dns_servers")
    if "allowInsecure" in normalized and "allow_insecure" not in normalized:
        normalized["allow_insecure"] = normalized.get("allowInsecure")
    if "allow_insecure" in normalized and "allowInsecure" not in normalized:
        normalized["allowInsecure"] = normalized.get("allow_insecure")
    if "domainResolver" in normalized and "domain_resolver" not in normalized:
        normalized["domain_resolver"] = normalized.get("domainResolver")
    if "domain_resolver" in normalized and "domainResolver" not in normalized:
        normalized["domainResolver"] = normalized.get("domain_resolver")
    if "packetEncoding" in normalized and "packet_encoding" not in normalized:
        normalized["packet_encoding"] = normalized.get("packetEncoding")
    if "packet_encoding" in normalized and "packetEncoding" not in normalized:
        normalized["packetEncoding"] = normalized.get("packet_encoding")
    if "rawSingBoxConfig" in normalized and "raw_sing_box_config" not in normalized:
        normalized["raw_sing_box_config"] = normalized.get("rawSingBoxConfig")
    if "raw_sing_box_config" in normalized and "rawSingBoxConfig" not in normalized:
        normalized["rawSingBoxConfig"] = normalized.get("raw_sing_box_config")
    if "rawXrayConfig" in normalized and "raw_xray_config" not in normalized:
        normalized["raw_xray_config"] = normalized.get("rawXrayConfig")
    if "raw_xray_config" in normalized and "rawXrayConfig" not in normalized:
        normalized["rawXrayConfig"] = normalized.get("raw_xray_config")
    return _apply_admin_mobile_defaults(normalized)


def _config_is_complete(payload: Dict[str, Any]) -> bool:
    normalized = _apply_admin_mobile_defaults(_normalize_vpn_payload_keys(payload))
    server = str(normalized.get("server") or "").strip()
    uuid = str(normalized.get("uuid") or "").strip()
    try:
        port = int(normalized.get("port") or 0)
    except (TypeError, ValueError):
        port = 0
    return bool(server and uuid and port > 0)


def _compose_vpn_payload_for_location(row: Dict[str, Any], *, requested_location_code: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    default_payload = settings.default_vpn_payload()
    if default_payload:
        payload.update(default_payload)
    overrides = settings.location_vpn_payloads().get(str(row.get("code") or "").strip())
    if overrides:
        payload.update(overrides)
    stored = row.get("vpn_payload")
    if isinstance(stored, dict) and stored:
        payload.update(stored)

    payload = _apply_admin_mobile_defaults(_normalize_vpn_payload_keys(payload))
    if not payload:
        return {}

    payload.setdefault("location_code", requested_location_code or row.get("code"))
    payload.setdefault("resolved_location_code", row.get("code"))
    payload.setdefault("remark", row.get("name_en") or row.get("name_ru") or row.get("code"))
    payload.setdefault("display_name", row.get("name_en") or row.get("name_ru") or row.get("code"))
    return payload


def _pick_virtual_location(code: str) -> Optional[Dict[str, Any]]:
    rows = list_locations(active_only=True)
    if not rows:
        return None

    def candidates(predicate) -> List[Dict[str, Any]]:
        return [row for row in rows if predicate(row) and _compose_vpn_payload_for_location(row)]

    if code == "auto-fastest":
        picks = candidates(lambda row: row.get("code") not in {"auto-fastest", "auto-reserve"} and row.get("status") == "online" and row.get("is_recommended"))
        if picks:
            return picks[0]
        picks = candidates(lambda row: row.get("code") not in {"auto-fastest", "auto-reserve"} and row.get("status") == "online")
        if picks:
            return picks[0]
    if code == "auto-reserve":
        picks = candidates(lambda row: row.get("code") not in {"auto-fastest", "auto-reserve"} and row.get("status") == "online" and row.get("is_reserve"))
        if picks:
            return picks[0]
        picks = candidates(lambda row: row.get("code") not in {"auto-fastest", "auto-reserve"} and row.get("status") == "online")
        if len(picks) >= 2:
            return picks[1]
        if picks:
            return picks[0]
    return None


def sync_locations_catalog() -> None:
    locations = _load_default_locations()
    if not locations:
        return

    default_codes = [item["code"] for item in locations]
    with db() as conn:
        with conn.cursor() as cur:
            for item in locations:
                data = dict(item)
                data["location_source"] = "catalog"
                data["is_deleted"] = bool(data.get("is_deleted", False))
                if not data.get("vpn_payload"):
                    data["vpn_payload"] = _compose_vpn_payload_for_location(data)
                data["vpn_payload"] = Jsonb(data.get("vpn_payload") or {})
                cur.execute(
                    """
                    INSERT INTO locations (code, name_ru, name_en, country_code, is_active, is_recommended, is_reserve, status, sort_order, vpn_payload, is_deleted, location_source)
                    VALUES (%(code)s, %(name_ru)s, %(name_en)s, %(country_code)s, %(is_active)s, %(is_recommended)s, %(is_reserve)s, %(status)s, %(sort_order)s, %(vpn_payload)s, %(is_deleted)s, %(location_source)s)
                    ON CONFLICT (code) DO UPDATE SET
                        -- Preserve admin-edited catalog rows across restarts.
                        -- Bootstrap should only backfill missing defaults, not overwrite
                        -- mutable values changed from the admin panel.
                        name_ru = CASE
                            WHEN COALESCE(NULLIF(BTRIM(locations.name_ru), ''), NULL) IS NULL THEN EXCLUDED.name_ru
                            ELSE locations.name_ru
                        END,
                        name_en = CASE
                            WHEN COALESCE(NULLIF(BTRIM(locations.name_en), ''), NULL) IS NULL THEN EXCLUDED.name_en
                            ELSE locations.name_en
                        END,
                        country_code = CASE
                            WHEN COALESCE(NULLIF(BTRIM(locations.country_code), ''), NULL) IS NULL THEN EXCLUDED.country_code
                            ELSE locations.country_code
                        END,
                        is_active = locations.is_active,
                        is_recommended = locations.is_recommended,
                        is_reserve = locations.is_reserve,
                        status = CASE
                            WHEN COALESCE(NULLIF(BTRIM(locations.status), ''), NULL) IS NULL THEN EXCLUDED.status
                            ELSE locations.status
                        END,
                        sort_order = CASE
                            WHEN locations.sort_order IS NULL THEN EXCLUDED.sort_order
                            ELSE locations.sort_order
                        END,
                        vpn_payload = CASE
                            WHEN locations.vpn_payload = '{}'::jsonb THEN EXCLUDED.vpn_payload
                            ELSE locations.vpn_payload
                        END,
                        is_deleted = locations.is_deleted,
                        location_source = CASE
                            WHEN COALESCE(NULLIF(BTRIM(locations.location_source), ''), 'catalog') = 'admin' THEN 'admin'
                            ELSE 'catalog'
                        END,
                        updated_at = NOW()
                    """,
                    data,
                )

            placeholders = ", ".join(["%s"] * len(default_codes))
            cur.execute(
                f"""
                UPDATE locations
                SET is_active = FALSE,
                    is_recommended = FALSE,
                    is_reserve = FALSE,
                    status = CASE WHEN status = 'online' THEN 'offline' ELSE status END,
                    updated_at = NOW()
                WHERE is_deleted = FALSE
                  AND location_source = 'catalog'
                  AND code NOT IN ({placeholders})
                """,
                tuple(default_codes),
            )
        conn.commit()


def _normalize_location_source(value: Any) -> str:
    normalized = str(value or "catalog").strip().lower()
    return "admin" if normalized == "admin" else "catalog"


def _as_positive_int(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _normalize_device_limit_override(value: Any) -> Optional[int]:
    parsed = _as_positive_int(value)
    if parsed is None:
        return None
    # V2: per-user override must bypass the global default ceiling.
    # Global max remains a default/plan cap for regular users,
    # but selected users may explicitly receive a higher manual limit.
    return parsed


def _resolve_effective_device_limit(plan_limit: Any = None, user_override: Any = None) -> int:
    override_limit = _normalize_device_limit_override(user_override)
    if override_limit is not None:
        return override_limit
    plan_value = _as_positive_int(plan_limit)
    if plan_value is not None:
        return min(plan_value, settings.VPN_MAX_DEVICES_PER_ACCOUNT)
    default_limit = _as_positive_int(settings.VPN_DEFAULT_DEVICE_LIMIT) or 1
    return min(default_limit, settings.VPN_MAX_DEVICES_PER_ACCOUNT)


def _normalize_user(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    return {
        "id": row["id"],
        "telegram_id": row["telegram_id"],
        "username": row.get("username"),
        "first_name": row.get("first_name"),
        "last_name": row.get("last_name"),
        "language": row.get("language") or "ru",
        "status": row.get("status") or "active",
        "device_limit_override": _normalize_device_limit_override(row.get("device_limit_override")),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            return _normalize_user(cur.fetchone())


def get_user_by_telegram_id(telegram_id: int) -> Optional[Dict[str, Any]]:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users WHERE telegram_id = %s", (telegram_id,))
            return _normalize_user(cur.fetchone())


def upsert_telegram_user(payload: Dict[str, Any]) -> Dict[str, Any]:
    telegram_id = int(payload["telegram_id"])
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (telegram_id, username, first_name, last_name, language, status)
                VALUES (%s, %s, %s, %s, %s, COALESCE(%s, 'active'))
                ON CONFLICT (telegram_id) DO UPDATE SET
                    username = COALESCE(EXCLUDED.username, users.username),
                    first_name = COALESCE(EXCLUDED.first_name, users.first_name),
                    last_name = COALESCE(EXCLUDED.last_name, users.last_name),
                    language = CASE
                        WHEN users.language IS NULL OR users.language = '' THEN COALESCE(EXCLUDED.language, 'ru')
                        ELSE users.language
                    END,
                    updated_at = NOW()
                RETURNING *
                """,
                (
                    telegram_id,
                    payload.get("username"),
                    payload.get("first_name"),
                    payload.get("last_name"),
                    payload.get("language") or "ru",
                    payload.get("status"),
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return _normalize_user(row)


def set_user_language(user_id: int, language: str) -> Dict[str, Any]:
    language = "en" if language == "en" else "ru"
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET language = %s, updated_at = NOW() WHERE id = %s RETURNING *", (language, user_id))
            row = cur.fetchone()
        conn.commit()
    return _normalize_user(row)


def set_user_status_by_telegram(telegram_id: int, status: str, admin_name: str, note: str) -> Dict[str, Any]:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET status = %s, updated_at = NOW() WHERE telegram_id = %s RETURNING *", (status, telegram_id))
            row = cur.fetchone()
            if not row:
                raise ValueError("User not found")
            cur.execute(
                "INSERT INTO admin_notes (user_id, admin_name, note) VALUES (%s, %s, %s)",
                (row["id"], admin_name, note),
            )
        conn.commit()
    return _normalize_user(row)


def get_active_plans() -> List[Dict[str, Any]]:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM plans WHERE is_active = TRUE ORDER BY duration_days ASC, price_rub ASC")
            return [dict(row) for row in cur.fetchall()]


def get_all_plans() -> List[Dict[str, Any]]:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM plans ORDER BY duration_days ASC, price_rub ASC")
            return [dict(row) for row in cur.fetchall()]


def get_plan_by_code(code: str) -> Optional[Dict[str, Any]]:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM plans WHERE code = %s", (code,))
            row = cur.fetchone()
            return dict(row) if row else None


def refresh_subscription_statuses(user_id: Optional[int] = None) -> None:
    query = """
        UPDATE subscriptions
        SET status = CASE
            WHEN starts_at <= NOW() AND expires_at >= NOW() THEN 'active'
            WHEN starts_at > NOW() THEN 'pending'
            ELSE 'expired'
        END,
        updated_at = NOW()
    """
    args: Tuple[Any, ...] = tuple()
    if user_id is not None:
        query += " WHERE user_id = %s"
        args = (user_id,)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, args)
        conn.commit()


def _subscription_select(where_sql: str) -> str:
    return f"""
        SELECT s.*, p.code AS plan_code, p.name_ru AS plan_name_ru, p.name_en AS plan_name_en,
               p.name_ru, p.name_en, p.price_rub, p.duration_days, p.device_limit
        FROM subscriptions s
        JOIN plans p ON p.id = s.plan_id
        {where_sql}
        ORDER BY s.expires_at DESC
        LIMIT 1
    """



def get_current_subscription(user_id: int) -> Optional[Dict[str, Any]]:
    refresh_subscription_statuses(user_id)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(_subscription_select("WHERE s.user_id = %s AND s.status = 'active'"), (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def get_latest_subscription(user_id: int) -> Optional[Dict[str, Any]]:
    refresh_subscription_statuses(user_id)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(_subscription_select("WHERE s.user_id = %s"), (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def get_user_devices(user_id: int) -> List[Dict[str, Any]]:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM devices WHERE user_id = %s AND is_active = TRUE ORDER BY last_seen_at DESC, created_at DESC",
                (user_id,),
            )
            return [dict(row) for row in cur.fetchall()]


def get_user_subscription_view(user_id: int) -> Dict[str, Any]:
    user = get_user_by_id(user_id)
    subscription = get_current_subscription(user_id)
    latest = subscription or get_latest_subscription(user_id)
    devices = get_user_devices(user_id)
    allowed_limit = _resolve_effective_device_limit(
        (latest or {}).get("device_limit"),
        (user or {}).get("device_limit_override"),
    )
    return {
        "subscription": latest,
        "is_active": bool(subscription),
        "devices": devices,
        "devices_used": len(devices),
        "device_limit": allowed_limit,
        "device_limit_override": (user or {}).get("device_limit_override"),
    }


def register_device(user_id: int, platform: str, device_name: str, device_fingerprint: str) -> Dict[str, Any]:
    user = get_user_by_id(user_id)
    if not user:
        raise ValueError("User not found")
    if user["status"] == "blocked":
        raise PermissionError("User is blocked")
    subscription = get_current_subscription(user_id)
    if not subscription:
        raise PermissionError("Active subscription required")
    if not settings.VPN_NEW_ACTIVATIONS_ENABLED:
        raise PermissionError("New activations are disabled")
    allowed_limit = _resolve_effective_device_limit(subscription.get("device_limit"), user.get("device_limit_override"))
    existing = get_user_devices(user_id)
    for item in existing:
        if item["device_fingerprint"] == device_fingerprint:
            with db() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE devices
                        SET platform = %s, device_name = %s, is_active = TRUE, last_seen_at = NOW()
                        WHERE id = %s
                        RETURNING *
                        """,
                        (platform, device_name, item["id"]),
                    )
                    row = cur.fetchone()
                conn.commit()
            return dict(row)
    if len(existing) >= allowed_limit:
        raise PermissionError(f"Device limit reached ({allowed_limit})")
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO devices (user_id, platform, device_name, device_fingerprint)
                VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (user_id, platform, device_name, device_fingerprint),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row)


def delete_device(user_id: int, device_id: int) -> Optional[Dict[str, Any]]:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM devices WHERE user_id = %s AND id = %s RETURNING *", (user_id, device_id))
            row = cur.fetchone()
        conn.commit()
    if row:
        enqueue_notification(
            user_id=user_id,
            event_type="device_removed",
            unique_key=f"device_removed:{row['id']}:{int(datetime.now(timezone.utc).timestamp())}",
            payload={
                "platform": row.get("platform"),
                "device_name": row.get("device_name"),
            },
        )
        return dict(row)
    return None


def list_locations(active_only: bool = True) -> List[Dict[str, Any]]:
    query = "SELECT * FROM locations WHERE is_deleted = FALSE"
    if active_only:
        query += " AND is_active = TRUE"
    query += " ORDER BY sort_order ASC, id ASC"
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return [dict(row) for row in cur.fetchall()]


def _normalize_location_mutation_payload(payload: Dict[str, Any], *, default_status: str = "offline") -> Dict[str, Any]:
    data = dict(payload or {})
    data["code"] = str(data.get("code") or "").strip()
    data["name_ru"] = str(data.get("name_ru") or "").strip()
    data["name_en"] = str(data.get("name_en") or data.get("name_ru") or "").strip()
    country_code = data.get("country_code")
    data["country_code"] = str(country_code).strip().upper() or None if country_code is not None else None
    data["status"] = str(data.get("status") or default_status).strip().lower() or default_status
    if data["status"] not in {"online", "offline", "reserve"}:
        data["status"] = default_status
    try:
        data["sort_order"] = int(data.get("sort_order") or 100)
    except (TypeError, ValueError):
        data["sort_order"] = 100
    data["is_active"] = bool(data.get("is_active", True))
    data["is_recommended"] = bool(data.get("is_recommended", False))
    data["is_reserve"] = bool(data.get("is_reserve", False))
    vpn_payload = _apply_admin_mobile_defaults(_normalize_vpn_payload_keys(data.get("vpn_payload") or {}))
    if data["code"] and not vpn_payload.get("location_code"):
        vpn_payload["location_code"] = data["code"]
    if data["name_en"] and not vpn_payload.get("remark"):
        vpn_payload["remark"] = data["name_en"]
    data["vpn_payload"] = vpn_payload
    return data



def _insert_or_upsert_location(cur: psycopg.Cursor, data: Dict[str, Any]) -> Dict[str, Any]:
    db_data = dict(data)
    db_data["vpn_payload"] = Jsonb(db_data.get("vpn_payload") or {})
    cur.execute(
        """
        INSERT INTO locations (code, name_ru, name_en, country_code, is_active, is_recommended, is_reserve, status, sort_order, vpn_payload, is_deleted, location_source)
        VALUES (%(code)s, %(name_ru)s, %(name_en)s, %(country_code)s, %(is_active)s, %(is_recommended)s, %(is_reserve)s, %(status)s, %(sort_order)s, %(vpn_payload)s, %(is_deleted)s, %(location_source)s)
        ON CONFLICT (code) DO UPDATE SET
            name_ru = EXCLUDED.name_ru,
            name_en = EXCLUDED.name_en,
            country_code = EXCLUDED.country_code,
            is_active = EXCLUDED.is_active,
            is_recommended = EXCLUDED.is_recommended,
            is_reserve = EXCLUDED.is_reserve,
            status = EXCLUDED.status,
            sort_order = EXCLUDED.sort_order,
            vpn_payload = EXCLUDED.vpn_payload,
            is_deleted = FALSE,
            location_source = EXCLUDED.location_source,
            updated_at = NOW()
        RETURNING *
        """,
        db_data,
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("Location was not saved")
    return dict(row)



def _is_locations_sequence_conflict(exc: Exception) -> bool:
    text = str(exc).lower()
    constraint_name = str(getattr(getattr(exc, "diag", None), "constraint_name", "") or "").lower()
    return (
        "duplicate key value violates unique constraint" in text
        and ("locations_pkey" in text or constraint_name == "locations_pkey")
    )



def create_location(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = _normalize_location_mutation_payload(payload)
    if not data["code"]:
        raise ValueError("code is required")
    if not data["name_ru"]:
        raise ValueError("name_ru is required")
    if not data["name_en"]:
        raise ValueError("name_en is required")
    data["is_deleted"] = False
    data["location_source"] = _normalize_location_source(data.get("location_source") or "admin")
    with db() as conn:
        with conn.cursor() as cur:
            try:
                _resync_serial_sequence(cur, "locations")
                row = _insert_or_upsert_location(cur, data)
            except psycopg.Error as exc:
                conn.rollback()
                if not _is_locations_sequence_conflict(exc):
                    raise
                with conn.cursor() as retry_cur:
                    _resync_serial_sequence(retry_cur, "locations")
                    row = _insert_or_upsert_location(retry_cur, data)
        conn.commit()
    return row


def patch_location(location_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    updates = []
    values: List[Any] = []
    allowed = {"name_ru", "name_en", "country_code", "is_active", "is_recommended", "is_reserve", "status", "sort_order", "vpn_payload"}
    for key, value in payload.items():
        if key not in allowed:
            continue
        if key in {"name_ru", "name_en"}:
            value = str(value or "").strip()
        elif key == "country_code":
            value = str(value).strip().upper() or None if value is not None else None
        elif key == "status":
            value = str(value or "offline").strip() or "offline"
        elif key == "sort_order":
            try:
                value = int(value)
            except (TypeError, ValueError):
                value = 100
        elif key == "vpn_payload":
            value = dict(_apply_admin_mobile_defaults(_normalize_vpn_payload_keys(value or {})))
            if "name_en" in payload and payload.get("name_en") and not value.get("remark"):
                value["remark"] = str(payload.get("name_en") or "").strip()
            value = Jsonb(value)
        updates.append(f"{key} = %s")
        values.append(value)
    if not updates:
        raise ValueError("No valid fields to update")
    values.append(location_id)
    query = f"UPDATE locations SET {', '.join(updates)}, updated_at = NOW() WHERE id = %s AND is_deleted = FALSE RETURNING *"
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(values))
            row = cur.fetchone()
            if not row:
                raise ValueError("Location not found")
        conn.commit()
    return dict(row)


def delete_location(location_id: int) -> Dict[str, Any]:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE locations
                SET is_deleted = TRUE,
                    is_active = FALSE,
                    is_recommended = FALSE,
                    is_reserve = FALSE,
                    status = CASE WHEN status = 'online' THEN 'offline' ELSE status END,
                    updated_at = NOW()
                WHERE id = %s AND is_deleted = FALSE
                RETURNING *
                """,
                (location_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("Location not found")
        conn.commit()
    return dict(row)


def get_vpn_config_for_user(user_id: int, location_code: str) -> Dict[str, Any]:
    subscription = get_current_subscription(user_id)
    if not subscription:
        raise PermissionError("Active subscription required")

    if location_code in {"auto-fastest", "auto-reserve"}:
        row = _pick_virtual_location(location_code)
        if not row:
            raise ValueError("No active VLESS node is available for auto selection")
    else:
        with db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM locations WHERE code = %s AND is_active = TRUE AND is_deleted = FALSE LIMIT 1",
                    (location_code,),
                )
                row = cur.fetchone()
    if not row:
        raise ValueError("Location not found")

    payload = _compose_vpn_payload_for_location(dict(row), requested_location_code=location_code)
    if not payload:
        raise ValueError("VLESS config is not configured for this location")
    if not _config_is_complete(payload):
        raise ValueError("VLESS config is incomplete for this location")
    return payload

def create_payment_record(
    user_id: int,
    plan_id: int,
    provider: str,
    method: str,
    amount: float,
    currency: str,
    status: str,
    external_payment_id: Optional[str] = None,
    checkout_url: Optional[str] = None,
) -> Dict[str, Any]:
    payment_id = str(uuid4())
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO payments (id, user_id, plan_id, provider, method, amount, currency, status, external_payment_id, checkout_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (payment_id, user_id, plan_id, provider, method, amount, currency, status, external_payment_id, checkout_url),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row)


def update_payment(payment_id: str, **fields: Any) -> Dict[str, Any]:
    if not fields:
        raise ValueError("No fields to update")
    updates = []
    values = []
    for key, value in fields.items():
        updates.append(f"{key} = %s")
        values.append(value)
    if fields.get("status") == "paid":
        updates.append("paid_at = COALESCE(paid_at, NOW())")
    values.append(payment_id)
    query = f"UPDATE payments SET {', '.join(updates)} WHERE id = %s RETURNING *"
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(values))
            row = cur.fetchone()
            if not row:
                raise ValueError("Payment not found")
        conn.commit()
    return dict(row)


def get_payment_for_user(payment_id: str, user_id: int) -> Optional[Dict[str, Any]]:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT pay.*, p.code AS plan_code, p.name_ru AS plan_name_ru, p.name_en AS plan_name_en,
                       p.duration_days, p.device_limit
                FROM payments pay
                JOIN plans p ON p.id = pay.plan_id
                WHERE pay.id = %s AND pay.user_id = %s
                """,
                (payment_id, user_id),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def get_payment_by_internal_or_external(payment_ref: str) -> Optional[Dict[str, Any]]:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM payments WHERE id = %s OR external_payment_id = %s LIMIT 1",
                (payment_ref, payment_ref),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def activate_payment_and_extend_subscription(payment_id: str) -> Dict[str, Any]:
    payment = get_payment_by_internal_or_external(payment_id)
    if not payment:
        raise ValueError("Payment not found")
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM plans WHERE id = %s", (payment["plan_id"],))
            plan = cur.fetchone()
            cur.execute("SELECT * FROM users WHERE id = %s", (payment["user_id"],))
            user = cur.fetchone()
            if not plan or not user:
                raise ValueError("Plan or user not found")
            if user["status"] == "blocked":
                raise PermissionError("Blocked user cannot be activated")
            if payment["status"] != "paid":
                cur.execute(
                    "UPDATE payments SET status = 'paid', paid_at = COALESCE(paid_at, NOW()) WHERE id = %s RETURNING *",
                    (payment["id"],),
                )
                payment = dict(cur.fetchone())
            cur.execute(
                "SELECT * FROM subscriptions WHERE user_id = %s ORDER BY expires_at DESC LIMIT 1",
                (payment["user_id"],),
            )
            latest = cur.fetchone()
            start_at = now_utc()
            if latest and latest["expires_at"] and latest["expires_at"] > start_at:
                start_at = latest["expires_at"]
            expires_at = start_at + timedelta(days=int(plan["duration_days"]))
            cur.execute(
                """
                INSERT INTO subscriptions (user_id, plan_id, starts_at, expires_at, status)
                VALUES (%s, %s, %s, %s, 'active')
                RETURNING *
                """,
                (payment["user_id"], plan["id"], start_at, expires_at),
            )
            subscription = cur.fetchone()
        conn.commit()
    refresh_subscription_statuses(payment["user_id"])
    user_info = _normalize_user(user) or {}
    enqueue_notification(
        user_id=payment["user_id"],
        event_type="payment_paid",
        unique_key=f"payment_paid:{payment['id']}",
        payload={
            "payment_id": payment["id"],
            "plan_code": plan["code"],
            "plan_name_ru": plan["name_ru"],
            "plan_name_en": plan["name_en"],
            "duration_days": int(plan["duration_days"]),
            "device_limit": _resolve_effective_device_limit(plan["device_limit"], user_info.get("device_limit_override")),
            "expires_at": subscription["expires_at"].isoformat(),
        },
    )
    return payment


def list_admin_users(search: str = "", status_filter: str = "all") -> Dict[str, Any]:
    refresh_subscription_statuses()
    clauses = []
    values: List[Any] = []
    if search:
        clauses.append("(CAST(u.telegram_id AS TEXT) ILIKE %s OR COALESCE(u.username, '') ILIKE %s)")
        values.extend([f"%{search}%", f"%{search}%"])
    if status_filter == "blocked":
        clauses.append("u.status = 'blocked'")
    elif status_filter == "active":
        clauses.append("u.status = 'active' AND EXISTS (SELECT 1 FROM subscriptions s WHERE s.user_id = u.id AND s.status = 'active')")
    elif status_filter == "expired":
        clauses.append("u.status <> 'blocked' AND NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.user_id = u.id AND s.status = 'active')")
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    u.id AS user_id,
                    u.telegram_id,
                    u.username,
                    u.first_name,
                    u.last_name,
                    u.language,
                    u.status,
                    u.device_limit_override,
                    s.id AS subscription_id,
                    s.expires_at,
                    p.code AS plan_code,
                    p.name_ru AS plan_name_ru,
                    p.name_en AS plan_name_en,
                    p.device_limit,
                    COALESCE((SELECT COUNT(*) FROM devices d WHERE d.user_id = u.id AND d.is_active = TRUE), 0) AS devices_used
                FROM users u
                LEFT JOIN LATERAL (
                    SELECT * FROM subscriptions s1
                    WHERE s1.user_id = u.id
                    ORDER BY s1.expires_at DESC
                    LIMIT 1
                ) s ON TRUE
                LEFT JOIN plans p ON p.id = s.plan_id
                {where_sql}
                ORDER BY u.created_at DESC
                """,
                tuple(values),
            )
            items = []
            for row in cur.fetchall():
                item = dict(row)
                item["device_limit_override"] = _normalize_device_limit_override(item.get("device_limit_override"))
                item["device_limit"] = _resolve_effective_device_limit(item.get("device_limit"), item.get("device_limit_override"))
                items.append(item)
            cur.execute("SELECT COUNT(*) AS total FROM users")
            total = cur.fetchone()["total"]
            cur.execute("SELECT COUNT(*) AS total FROM users WHERE status = 'blocked'")
            blocked = cur.fetchone()["total"]
            cur.execute("SELECT COUNT(DISTINCT user_id) AS total FROM subscriptions WHERE status = 'active'")
            active = cur.fetchone()["total"]
    summary = {
        "total_users": total,
        "blocked_users": blocked,
        "active_subscriptions": active,
        "expired_or_no_subscription": max(total - blocked - active, 0),
    }
    return {"items": items, "summary": summary}


def admin_create_or_update_user(payload: Dict[str, Any], admin_name: str) -> Dict[str, Any]:
    plan = get_plan_by_code(payload["plan_code"])
    if not plan:
        raise ValueError("Plan not found")
    user = upsert_telegram_user(payload)
    if "device_limit_override" in payload:
        user = set_user_device_limit_override_by_telegram(int(user["telegram_id"]), payload.get("device_limit_override"), admin_name)["user"]
    refresh_subscription_statuses(user["id"])
    expires_at = payload.get("expires_at")
    if expires_at:
        if isinstance(expires_at, str):
            expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        else:
            expires_dt = expires_at
        starts_at = now_utc()
        if expires_dt <= starts_at:
            starts_at = expires_dt - timedelta(days=int(plan["duration_days"]))
    else:
        starts_at = now_utc()
        expires_dt = starts_at + timedelta(days=int(plan["duration_days"]))
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM subscriptions WHERE user_id = %s AND status = 'active' ORDER BY expires_at DESC, id DESC LIMIT 1",
                (user["id"],),
            )
            current = cur.fetchone()
            if not current:
                cur.execute(
                    "SELECT * FROM subscriptions WHERE user_id = %s ORDER BY expires_at DESC, id DESC LIMIT 1",
                    (user["id"],),
                )
                current = cur.fetchone()
            if current:
                cur.execute(
                    """
                    UPDATE subscriptions
                    SET plan_id = %s, starts_at = %s, expires_at = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (plan["id"], starts_at, expires_dt, current["id"]),
                )
                note = f"Manual access updated for plan {plan['code']}"
            else:
                cur.execute(
                    "INSERT INTO subscriptions (user_id, plan_id, starts_at, expires_at, status) VALUES (%s, %s, %s, %s, 'active')",
                    (user["id"], plan["id"], starts_at, expires_dt),
                )
                note = f"Manual access issued for plan {plan['code']}"
            cur.execute(
                "INSERT INTO admin_notes (user_id, admin_name, note) VALUES (%s, %s, %s)",
                (user["id"], admin_name, note),
            )
        conn.commit()
    refresh_subscription_statuses(user["id"])
    return get_user_snapshot_by_telegram(int(user["telegram_id"]))


def get_user_snapshot_by_telegram(telegram_id: int) -> Dict[str, Any]:
    user = get_user_by_telegram_id(telegram_id)
    if not user:
        raise ValueError("User not found")
    view = get_user_subscription_view(user["id"])
    return {
        "user": user,
        "subscription": view["subscription"],
        "devices": view["devices"],
        "devices_used": view["devices_used"],
        "device_limit": view["device_limit"],
        "device_limit_override": view.get("device_limit_override"),
    }


def extend_user_subscription_by_telegram(telegram_id: int, days_added: int, reason: str, admin_name: str) -> Dict[str, Any]:
    user = get_user_by_telegram_id(telegram_id)
    if not user:
        raise ValueError("User not found")
    if days_added <= 0:
        raise ValueError("days_added must be positive")
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM subscriptions WHERE user_id = %s ORDER BY expires_at DESC LIMIT 1", (user["id"],))
            sub = cur.fetchone()
            if not sub:
                plan = get_plan_by_code(settings.PLAN_MONTHLY_CODE) or get_all_plans()[0]
                starts_at = now_utc()
                expires_at = starts_at + timedelta(days=days_added)
                cur.execute(
                    "INSERT INTO subscriptions (user_id, plan_id, starts_at, expires_at, status) VALUES (%s, %s, %s, %s, 'active')",
                    (user["id"], plan["id"], starts_at, expires_at),
                )
            else:
                base = sub["expires_at"] if sub["expires_at"] > now_utc() else now_utc()
                new_expiry = base + timedelta(days=days_added)
                cur.execute(
                    "UPDATE subscriptions SET expires_at = %s, status = 'active', updated_at = NOW() WHERE id = %s",
                    (new_expiry, sub["id"]),
                )
            cur.execute(
                "INSERT INTO manual_extensions (user_id, days_added, reason, admin_name) VALUES (%s, %s, %s, %s)",
                (user["id"], days_added, reason, admin_name),
            )
        conn.commit()
    refresh_subscription_statuses(user["id"])
    return get_user_snapshot_by_telegram(telegram_id)


def set_user_device_limit_override_by_telegram(telegram_id: int, device_limit_override: Optional[int], admin_name: str) -> Dict[str, Any]:
    user = get_user_by_telegram_id(telegram_id)
    if not user:
        raise ValueError("User not found")
    normalized_override = _normalize_device_limit_override(device_limit_override)
    note = (
        f"Device limit override set to {normalized_override}"
        if normalized_override is not None
        else "Device limit override cleared (plan default)"
    )
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET device_limit_override = %s, updated_at = NOW() WHERE telegram_id = %s RETURNING *",
                (normalized_override, telegram_id),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("User not found")
            cur.execute(
                "INSERT INTO admin_notes (user_id, admin_name, note) VALUES (%s, %s, %s)",
                (row["id"], admin_name, note),
            )
        conn.commit()
    return get_user_snapshot_by_telegram(telegram_id)


def reset_user_devices_by_telegram(telegram_id: int, admin_name: str) -> Dict[str, Any]:
    user = get_user_by_telegram_id(telegram_id)
    if not user:
        raise ValueError("User not found")
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM devices WHERE user_id = %s AND is_active = TRUE", (user["id"],))
            devices = [dict(row) for row in cur.fetchall()]
            cur.execute("DELETE FROM devices WHERE user_id = %s", (user["id"],))
            cur.execute(
                "INSERT INTO admin_notes (user_id, admin_name, note) VALUES (%s, %s, %s)",
                (user["id"], admin_name, "Devices reset from admin panel"),
            )
        conn.commit()
    if devices:
        enqueue_notification(
            user_id=user["id"],
            event_type="device_removed",
            unique_key=f"device_reset:{user['id']}:{int(now_utc().timestamp())}",
            payload={"count": len(devices), "device_name": "all", "platform": "all"},
        )
    return get_user_snapshot_by_telegram(telegram_id)


def list_payments(status_filter: str = "all") -> List[Dict[str, Any]]:
    query = """
        SELECT pay.*, u.telegram_id, u.username, p.code AS plan_code, p.name_ru AS plan_name_ru, p.name_en AS plan_name_en
        FROM payments pay
        JOIN users u ON u.id = pay.user_id
        JOIN plans p ON p.id = pay.plan_id
    """
    values: Tuple[Any, ...] = tuple()
    if status_filter != "all":
        query += " WHERE pay.status = %s"
        values = (status_filter,)
    query += " ORDER BY pay.created_at DESC"
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, values)
            return [dict(row) for row in cur.fetchall()]


def export_payments_csv(status_filter: str = "all") -> str:
    rows = list_payments(status_filter)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["payment_id", "telegram_id", "username", "plan_code", "amount", "currency", "status", "external_payment_id", "created_at", "paid_at"])
    for row in rows:
        writer.writerow([
            row.get("id"),
            row.get("telegram_id"),
            row.get("username"),
            row.get("plan_code"),
            row.get("amount"),
            row.get("currency"),
            row.get("status"),
            row.get("external_payment_id"),
            row.get("created_at"),
            row.get("paid_at"),
        ])
    return output.getvalue()


def issue_auth_code(user_id: int, ttl_minutes: Optional[int] = None, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    ttl = max(1, int(ttl_minutes or settings.AUTH_CODE_TTL_MINUTES or 5))
    code = secrets.token_urlsafe(18)
    expires_at = now_utc() + timedelta(minutes=ttl)
    payload = meta or {}
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE auth_codes
                SET used_at = NOW()
                WHERE user_id = %s AND used_at IS NULL
                """,
                (user_id,),
            )
            cur.execute(
                """
                INSERT INTO auth_codes (code, user_id, expires_at, meta)
                VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (code, user_id, expires_at, Jsonb(payload)),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row)


def consume_auth_code(code: str) -> Optional[Dict[str, Any]]:
    normalized = (code or "").strip()
    if not normalized:
        return None
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM auth_codes
                WHERE code = %s
                FOR UPDATE
                """,
                (normalized,),
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                return None
            if row.get("used_at") is not None or row.get("expires_at") <= now_utc():
                conn.rollback()
                return None
            cur.execute(
                "UPDATE auth_codes SET used_at = NOW() WHERE code = %s",
                (normalized,),
            )
            cur.execute(
                "SELECT * FROM users WHERE id = %s",
                (row["user_id"],),
            )
            user = cur.fetchone()
        conn.commit()
    return _normalize_user(user)


def settings_snapshot() -> Dict[str, Any]:
    return {
        "app_name": settings.APP_NAME,
        "app_env": settings.APP_ENV,
        "languages": settings.APP_LANGS,
        "device_limit": settings.VPN_DEFAULT_DEVICE_LIMIT,
        "max_devices_per_account": settings.VPN_MAX_DEVICES_PER_ACCOUNT,
        "maintenance_mode": settings.VPN_MAINTENANCE_MODE,
        "new_activations_enabled": settings.VPN_NEW_ACTIVATIONS_ENABLED,
        "payments_enabled": settings.PAYMENTS_ENABLED,
        "payments_provider": settings.PAYMENTS_PROVIDER,
        "support_telegram_url": settings.SUPPORT_TELEGRAM_URL,
        "support_faq_ru": settings.SUPPORT_FAQ_RU,
        "support_faq_en": settings.SUPPORT_FAQ_EN,
        "bot_name": settings.BOT_NAME,
        "bot_username": settings.BOT_USERNAME,
        "open_app_url": settings.OPEN_APP_URL,
        "android_app_url": settings.ANDROID_APP_URL,
        "ios_app_url": settings.IOS_APP_URL,
        "settings_editable": settings.VPN_SETTINGS_EDITABLE,
        "locations_catalog_source": "env_override" if settings.DEFAULT_LOCATIONS_ENV_OVERRIDE_ENABLED else "builtin_mvp",
        "plans": get_all_plans(),
    }


def enqueue_notification(user_id: int, event_type: str, unique_key: str, payload: Dict[str, Any]) -> bool:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bot_notifications (unique_key, user_id, event_type, payload)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (unique_key) DO NOTHING
                RETURNING id
                """,
                (unique_key, user_id, event_type, Jsonb(payload or {})),
            )
            row = cur.fetchone()
        conn.commit()
    return bool(row)


def purge_stale_subscription_notifications() -> None:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM bot_notifications n
                WHERE n.sent_at IS NULL
                  AND n.event_type = 'subscription_expiring'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM (
                          SELECT DISTINCT ON (s.user_id) s.id, s.user_id, s.expires_at
                          FROM subscriptions s
                          WHERE s.status = 'active' AND s.expires_at > NOW()
                          ORDER BY s.user_id, s.expires_at DESC, s.id DESC
                      ) latest
                      WHERE latest.user_id = n.user_id
                        AND latest.expires_at <= NOW() + INTERVAL '1 day'
                        AND latest.id = CASE
                            WHEN COALESCE(n.payload->>'subscription_id', '') ~ '^[0-9]+$'
                                THEN (n.payload->>'subscription_id')::BIGINT
                            ELSE NULL
                        END
                  )
                """
            )
            cur.execute(
                """
                DELETE FROM bot_notifications n
                WHERE n.sent_at IS NULL
                  AND n.event_type = 'subscription_expired'
                  AND EXISTS (
                      SELECT 1
                      FROM subscriptions s
                      WHERE s.user_id = n.user_id
                        AND s.status = 'active'
                  )
                """
            )
        conn.commit()



def enqueue_subscription_notifications() -> None:
    refresh_subscription_statuses()
    purge_stale_subscription_notifications()
    now = now_utc()
    soon = now + timedelta(days=1)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT latest.id, latest.user_id, latest.expires_at, latest.plan_code, latest.name_ru, latest.name_en, latest.duration_days, latest.device_limit
                FROM (
                    SELECT DISTINCT ON (s.user_id)
                        s.id, s.user_id, s.expires_at, p.code AS plan_code, p.name_ru, p.name_en, p.duration_days, p.device_limit
                    FROM subscriptions s
                    JOIN plans p ON p.id = s.plan_id
                    WHERE s.status = 'active' AND s.expires_at > NOW()
                    ORDER BY s.user_id, s.expires_at DESC, s.id DESC
                ) latest
                WHERE latest.expires_at <= NOW() + INTERVAL '1 day'
                """
            )
            expiring = [dict(row) for row in cur.fetchall()]
            cur.execute(
                """
                SELECT DISTINCT ON (s.user_id)
                    s.id, s.user_id, s.expires_at, p.code AS plan_code, p.name_ru, p.name_en, p.duration_days, p.device_limit
                FROM subscriptions s
                JOIN plans p ON p.id = s.plan_id
                WHERE s.status = 'expired'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM subscriptions s2
                      WHERE s2.user_id = s.user_id
                        AND s2.status = 'active'
                  )
                ORDER BY s.user_id, s.expires_at DESC
                LIMIT 500
                """
            )
            expired = [dict(row) for row in cur.fetchall()]
    for row in expiring:
        user = get_user_by_id(int(row["user_id"])) or {}
        enqueue_notification(
            user_id=row["user_id"],
            event_type="subscription_expiring",
            unique_key=f"subscription_expiring:{row['id']}",
            payload={
                "subscription_id": row["id"],
                "expires_at": row["expires_at"].isoformat(),
                "plan_code": row["plan_code"],
                "plan_name_ru": row["name_ru"],
                "plan_name_en": row["name_en"],
                "duration_days": int(row["duration_days"]),
                "device_limit": _resolve_effective_device_limit(row["device_limit"], user.get("device_limit_override")),
            },
        )
    for row in expired:
        user = get_user_by_id(int(row["user_id"])) or {}
        enqueue_notification(
            user_id=row["user_id"],
            event_type="subscription_expired",
            unique_key=f"subscription_expired:{row['id']}",
            payload={
                "subscription_id": row["id"],
                "expires_at": row["expires_at"].isoformat(),
                "plan_code": row["plan_code"],
                "plan_name_ru": row["name_ru"],
                "plan_name_en": row["name_en"],
                "duration_days": int(row["duration_days"]),
                "device_limit": _resolve_effective_device_limit(row["device_limit"], user.get("device_limit_override")),
            },
        )



def list_pending_notifications(limit: int = 100) -> List[Dict[str, Any]]:
    purge_stale_subscription_notifications()
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT n.*, u.telegram_id, u.language, u.status AS user_status
                FROM bot_notifications n
                JOIN users u ON u.id = n.user_id
                WHERE n.sent_at IS NULL
                ORDER BY n.created_at ASC
                LIMIT %s
                """,
                (limit,),
            )
            rows = [dict(row) for row in cur.fetchall()]
    return rows


def mark_notification_sent(notification_id: int) -> None:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE bot_notifications SET sent_at = NOW() WHERE id = %s", (notification_id,))
        conn.commit()


def record_bot_error(source: str, context: str, error_message: str) -> None:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO bot_error_log (source, context, error_message) VALUES (%s, %s, %s)",
                (source, context, error_message[:4000]),
            )
        conn.commit()


def list_bot_errors(limit: int = 50) -> List[Dict[str, Any]]:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM bot_error_log ORDER BY created_at DESC LIMIT %s", (limit,))
            return [dict(row) for row in cur.fetchall()]


def list_broadcast_targets(statuses: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    statuses = statuses or ["active"]
    statuses = [item.strip().lower() for item in statuses if item]
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.id, u.telegram_id, u.language, u.status,
                       s.expires_at
                FROM users u
                LEFT JOIN LATERAL (
                    SELECT * FROM subscriptions s1
                    WHERE s1.user_id = u.id
                    ORDER BY s1.expires_at DESC
                    LIMIT 1
                ) s ON TRUE
                ORDER BY u.created_at DESC
                """
            )
            rows = [dict(row) for row in cur.fetchall()]
    result = []
    now = now_utc()
    for row in rows:
        if row["status"] == "blocked":
            user_bucket = "blocked"
        elif row.get("expires_at") and row["expires_at"] >= now:
            user_bucket = "active"
        else:
            user_bucket = "expired"
        if user_bucket in statuses:
            result.append(row)
    return result
