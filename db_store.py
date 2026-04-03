import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import psycopg
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


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def db() -> psycopg.Connection:
    return psycopg.connect(settings.DATABASE_URL, row_factory=dict_row)


def bootstrap() -> None:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()
    sync_plans_from_env()
    seed_locations_from_env()


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


def seed_locations_from_env() -> None:
    try:
        locations = json.loads(settings.DEFAULT_LOCATIONS_JSON or "[]")
    except json.JSONDecodeError:
        locations = []
    if not locations:
        return
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS count FROM locations")
            row = cur.fetchone()
            if row and row["count"] > 0:
                return
            for item in locations:
                cur.execute(
                    """
                    INSERT INTO locations (code, name_ru, name_en, country_code, is_active, is_recommended, is_reserve, status, sort_order)
                    VALUES (%(code)s, %(name_ru)s, %(name_en)s, %(country_code)s, %(is_active)s, %(is_recommended)s, %(is_reserve)s, %(status)s, %(sort_order)s)
                    ON CONFLICT (code) DO NOTHING
                    """,
                    item,
                )
        conn.commit()


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
    subscription = get_current_subscription(user_id)
    latest = subscription or get_latest_subscription(user_id)
    devices = get_user_devices(user_id)
    if latest:
        allowed_limit = min(int(latest["device_limit"]), settings.VPN_MAX_DEVICES_PER_ACCOUNT)
    else:
        allowed_limit = settings.VPN_DEFAULT_DEVICE_LIMIT
    return {
        "subscription": latest,
        "is_active": bool(subscription),
        "devices": devices,
        "devices_used": len(devices),
        "device_limit": allowed_limit,
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
    allowed_limit = min(int(subscription["device_limit"]), settings.VPN_MAX_DEVICES_PER_ACCOUNT)
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
    query = "SELECT * FROM locations"
    if active_only:
        query += " WHERE is_active = TRUE"
    query += " ORDER BY sort_order ASC, id ASC"
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return [dict(row) for row in cur.fetchall()]


def create_location(payload: Dict[str, Any]) -> Dict[str, Any]:
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO locations (code, name_ru, name_en, country_code, is_active, is_recommended, is_reserve, status, sort_order)
                VALUES (%(code)s, %(name_ru)s, %(name_en)s, %(country_code)s, %(is_active)s, %(is_recommended)s, %(is_reserve)s, %(status)s, %(sort_order)s)
                RETURNING *
                """,
                payload,
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row)


def patch_location(location_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    updates = []
    values: List[Any] = []
    allowed = {"name_ru", "name_en", "country_code", "is_active", "is_recommended", "is_reserve", "status", "sort_order"}
    for key, value in payload.items():
        if key in allowed:
            updates.append(f"{key} = %s")
            values.append(value)
    if not updates:
        raise ValueError("No valid fields to update")
    values.append(location_id)
    query = f"UPDATE locations SET {', '.join(updates)}, updated_at = NOW() WHERE id = %s RETURNING *"
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(values))
            row = cur.fetchone()
            if not row:
                raise ValueError("Location not found")
        conn.commit()
    return dict(row)


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
            "device_limit": min(int(plan["device_limit"]), settings.VPN_MAX_DEVICES_PER_ACCOUNT),
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
                item["device_limit"] = min(int(item.get("device_limit") or settings.VPN_DEFAULT_DEVICE_LIMIT), settings.VPN_MAX_DEVICES_PER_ACCOUNT)
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
                "INSERT INTO subscriptions (user_id, plan_id, starts_at, expires_at, status) VALUES (%s, %s, %s, %s, 'active')",
                (user["id"], plan["id"], starts_at, expires_dt),
            )
            cur.execute(
                "INSERT INTO admin_notes (user_id, admin_name, note) VALUES (%s, %s, %s)",
                (user["id"], admin_name, f"Manual access issued for plan {plan['code']}"),
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


def enqueue_subscription_notifications() -> None:
    refresh_subscription_statuses()
    now = now_utc()
    soon = now + timedelta(days=1)
    with db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.id, s.user_id, s.expires_at, p.code AS plan_code, p.name_ru, p.name_en, p.duration_days, p.device_limit
                FROM subscriptions s
                JOIN plans p ON p.id = s.plan_id
                WHERE s.status = 'active' AND s.expires_at > NOW() AND s.expires_at <= NOW() + INTERVAL '1 day'
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
                "device_limit": min(int(row["device_limit"]), settings.VPN_MAX_DEVICES_PER_ACCOUNT),
            },
        )
    for row in expired:
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
                "device_limit": min(int(row["device_limit"]), settings.VPN_MAX_DEVICES_PER_ACCOUNT),
            },
        )


def list_pending_notifications(limit: int = 100) -> List[Dict[str, Any]]:
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
