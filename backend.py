from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import secrets
from uuid import uuid4

import jwt
import requests
from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
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
    export_payments_csv,
    get_active_plans,
    get_payment_by_internal_or_external,
    get_payment_for_user,
    get_plan_by_code,
    get_user_by_id,
    get_user_by_telegram_id,
    get_user_snapshot_by_telegram,
    get_user_subscription_view,
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
    set_user_language,
    set_user_status_by_telegram,
    settings_snapshot,
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


class CodeAuthIn(TelegramAuthIn):
    code: str


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


class LocationPatchIn(BaseModel):
    name_ru: Optional[str] = None
    name_en: Optional[str] = None
    country_code: Optional[str] = None
    is_active: Optional[bool] = None
    is_recommended: Optional[bool] = None
    is_reserve: Optional[bool] = None
    status: Optional[str] = None
    sort_order: Optional[int] = None


class BroadcastIn(BaseModel):
    text: str = ""
    statuses: List[str] = Field(default_factory=lambda: ["active"])


class TestSendIn(BaseModel):
    telegram_id: int
    text: str


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



def issue_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(days=30),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")



def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    try:
        payload = jwt.decode(credentials.credentials, settings.JWT_SECRET, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user



def require_admin(credentials: HTTPBasicCredentials = Depends(basic_security)) -> str:
    valid_user = secrets.compare_digest(credentials.username or "", settings.ADMIN_BASIC_USER)
    valid_pass = secrets.compare_digest(credentials.password or "", settings.ADMIN_BASIC_PASS)
    if not (valid_user and valid_pass):
        raise HTTPException(status_code=401, detail="Invalid admin credentials", headers={"WWW-Authenticate": "Basic"})
    return credentials.username


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "service": settings.APP_NAME}


@app.post("/auth/telegram")
def auth_telegram(payload: TelegramAuthIn) -> Dict[str, Any]:
    existing = get_user_by_telegram_id(payload.telegram_id)
    user = upsert_telegram_user(payload.model_dump())
    token = issue_token(user["id"])
    return {"ok": True, "token": token, "user": user, "is_new": existing is None}


@app.post("/auth/code")
def auth_code(payload: CodeAuthIn) -> Dict[str, Any]:
    if not settings.AUTH_ALLOW_DEV_CODE:
        raise HTTPException(status_code=403, detail="Code login disabled")
    if payload.code != settings.AUTH_DEV_LOGIN_CODE:
        raise HTTPException(status_code=401, detail="Invalid code")
    existing = get_user_by_telegram_id(payload.telegram_id)
    user = upsert_telegram_user(payload.model_dump(exclude={"code"}))
    token = issue_token(user["id"])
    return {"ok": True, "token": token, "user": user, "is_new": existing is None}


@app.get("/auth/me")
def auth_me(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    view = get_user_subscription_view(user["id"])
    return {"ok": True, "user": user, **view}


@app.patch("/users/me/language")
def patch_language(payload: LanguageIn, user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    updated = set_user_language(user["id"], payload.language)
    return {"ok": True, "user": updated}


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
    return {"ok": True, "items": list_locations(active_only=True)}


@app.get("/locations/status")
def locations_status() -> Dict[str, Any]:
    rows = list_locations(active_only=False)
    return {"ok": True, "items": [{"code": row["code"], "status": row["status"], "is_active": row["is_active"]} for row in rows]}


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
        item = admin_create_or_update_user(payload.model_dump(), admin_name)
        return {"ok": True, "item": item}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    return {"ok": True, "items": list_locations(active_only=False)}


@app.post("/api/infra/admin/vpn/locations")
def admin_locations_create(payload: LocationIn, admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    _ = admin_name
    return {"ok": True, "item": create_location(payload.model_dump())}


@app.patch("/api/infra/admin/vpn/locations/{location_id}")
def admin_locations_patch(location_id: int, payload: LocationPatchIn, admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    _ = admin_name
    data = {key: value for key, value in payload.model_dump().items() if value is not None}
    try:
        return {"ok": True, "item": patch_location(location_id, data)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/infra/admin/vpn/settings")
def admin_settings(admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    _ = admin_name
    sync_plans_from_env()
    return {"ok": True, "settings": settings_snapshot()}


@app.post("/api/infra/admin/vpn/settings")
def admin_settings_save(admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    _ = admin_name
    if not settings.VPN_SETTINGS_EDITABLE:
        return {
            "ok": False,
            "read_only": True,
            "message": "Settings are loaded from Railway env. Change env values and redeploy.",
            "settings": settings_snapshot(),
        }
    return {"ok": True, "message": "Editable mode is enabled, but env-first mode is recommended.", "settings": settings_snapshot()}



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


@app.get("/api/infra/admin/vpn/errors")
def admin_errors(limit: int = Query(default=50, ge=1, le=500), admin_name: str = Depends(require_admin)) -> Dict[str, Any]:
    _ = admin_name
    return {"ok": True, "items": list_bot_errors(limit=limit)}
