"""3X-UI client sync helpers.

The backend DB remains the source of truth. 3X-UI is treated as the runtime
Xray control plane: managed clients are added/removed from selected inbounds so
old raw VLESS links stop working after a device is deleted.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin

import requests
try:
    import urllib3
    from urllib3.exceptions import InsecureRequestWarning
except Exception:  # pragma: no cover - urllib3 is a requests dependency
    urllib3 = None
    InsecureRequestWarning = None

logger = logging.getLogger("inet.vpn.xui")


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _disable_insecure_https_warning() -> None:
    if urllib3 is not None and InsecureRequestWarning is not None:
        urllib3.disable_warnings(InsecureRequestWarning)


_SSL_FALLBACK_WARNED: set[str] = set()


class XUIError(RuntimeError):
    pass


@dataclass(frozen=True)
class XUIServerConfig:
    key: str
    base_url: str
    username: str
    password: str
    token: str = ""
    timeout_sec: int = 8
    verify_ssl: bool = True


class XUIClient:
    def __init__(self, cfg: XUIServerConfig):
        self.cfg = cfg
        self.session = requests.Session()
        if cfg.token:
            # Different 3X-UI builds/proxies accept different token header names.
            # Keep Authorization for modern deployments and add explicit aliases for
            # admin diagnostics / reverse-proxy integrations.
            self.session.headers.update({
                "Authorization": f"Bearer {cfg.token}",
                "X-API-Token": str(cfg.token),
                "X-Token": str(cfg.token),
            })
        self.session.headers.update({"User-Agent": "inet-vpn-backend/xui-sync"})

    def _url(self, path: str) -> str:
        base = str(self.cfg.base_url or "").strip().rstrip("/") + "/"
        return urljoin(base, path.lstrip("/"))

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", max(1, int(self.cfg.timeout_sec or 8)))
        verify_ssl = bool(kwargs.pop("verify", bool(self.cfg.verify_ssl)))
        request_url = self._url(path)

        if not verify_ssl:
            _disable_insecure_https_warning()

        try:
            kwargs["verify"] = verify_ssl
            return self.session.request(method.upper(), request_url, **kwargs)
        except requests.exceptions.SSLError:
            # Compatibility fallback for old 3X-UI panels that are exposed by IP
            # or use a self-signed certificate. This restores the old behavior
            # without breaking sync after XUI_VERIFY_SSL=true was accidentally set.
            if verify_ssl and _env_bool("XUI_SSL_AUTO_FALLBACK", True):
                warn_key = str(self.cfg.key or self.cfg.base_url or "default")
                if warn_key not in _SSL_FALLBACK_WARNED:
                    logger.warning(
                        "[xui-sync] SSL verification failed for %s; retrying once with verify_ssl=false. "
                        "For production, use a domain with a valid SSL certificate and keep XUI_VERIFY_SSL=true.",
                        warn_key,
                    )
                    _SSL_FALLBACK_WARNED.add(warn_key)
                _disable_insecure_https_warning()
                kwargs["verify"] = False
                return self.session.request(method.upper(), request_url, **kwargs)
            raise

    def login(self) -> None:
        # Prefer the normal form/json login when username+password are configured.
        # API tokens are still attached to headers, but some 3X-UI builds do not
        # accept Bearer auth for /panel/api/* and require the session cookie.
        if not self.cfg.username or not self.cfg.password:
            if self.cfg.token:
                return
            raise XUIError(f"3X-UI server {self.cfg.key}: username/password required")

        # 3X-UI login is form-based in normal panel builds. Keep a JSON fallback
        # for forks/reverse proxies that accept JSON only.
        candidates = [
            ("data", {"username": self.cfg.username, "password": self.cfg.password}),
            ("json", {"username": self.cfg.username, "password": self.cfg.password}),
        ]
        last_error = ""
        for mode, payload in candidates:
            try:
                kwargs = {mode: payload}
                resp = self._request("POST", "/login", **kwargs)
                last_error = f"HTTP {resp.status_code}: {(resp.text or '')[:200]}"
                if 200 <= resp.status_code < 300 and self.session.cookies:
                    return
                try:
                    data = resp.json()
                except Exception:
                    data = None
                if isinstance(data, dict) and data.get("success") is True:
                    return
            except Exception as exc:  # pragma: no cover - network dependent
                last_error = str(exc)
        if self.cfg.token:
            # Token may still be accepted by the inbounds endpoints even if the
            # cookie login is blocked by a fork/reverse proxy. Let the caller try
            # the protected endpoint with token headers and surface that result.
            return
        raise XUIError(f"3X-UI login failed for {self.cfg.key}: {last_error}")

    def _response_summary(self, resp: requests.Response, *, body_limit: int = 500) -> Dict[str, Any]:
        text = ""
        try:
            text = resp.text or ""
        except Exception:
            text = ""
        body = text[:body_limit]
        if len(text) > body_limit:
            body += "…"
        return {
            "status_code": int(resp.status_code),
            "ok": bool(200 <= resp.status_code < 300),
            "content_type": resp.headers.get("content-type", ""),
            "location": resp.headers.get("location", ""),
            "set_cookie": bool(resp.headers.get("set-cookie")),
            "cookies": sorted([c.name for c in self.session.cookies]),
            "json": _safe_json(resp),
            "body_snippet": body,
        }

    def diagnose(self) -> Dict[str, Any]:
        """Return a safe, admin-facing connectivity/login diagnostic report.

        The report intentionally does not include passwords or token values. It is
        used by the admin panel to show why a 3X-UI registry test failed instead
        of only returning an opaque HTTP 403/502.
        """
        result: Dict[str, Any] = {
            "server_key": self.cfg.key,
            "base_url": self.cfg.base_url,
            "verify_ssl": bool(self.cfg.verify_ssl),
            "timeout_sec": int(self.cfg.timeout_sec or 8),
            "credentials": {
                "username_set": bool(str(self.cfg.username or "").strip()),
                "password_set": bool(str(self.cfg.password or "").strip()),
                "token_set": bool(str(self.cfg.token or "").strip()),
            },
            "checks": [],
            "login_attempts": [],
            "inbound_attempts": [],
            "hints": [],
        }

        base_text = str(self.cfg.base_url or "").strip()
        if not base_text:
            result["hints"].append("base_url пустой: укажи https://IP:2053/WebBasePath")
            return result
        if "://" not in base_text:
            result["hints"].append("base_url должен начинаться с http:// или https://")
        if "/login" in base_text or "/panel/api" in base_text:
            result["hints"].append("base_url должен быть только до WebBasePath, без /login и без /panel/api/...")
        if base_text.startswith("https://") and not self.cfg.verify_ssl:
            result["hints"].append("verify SSL выключен — это нормально для HTTPS по IP/self-signed, но для домена лучше включать SSL.")
        if not self.cfg.username or not self.cfg.password:
            if self.cfg.token:
                result["hints"].append("username/password пустые: будет проверяться только API token.")
            else:
                result["hints"].append("Не заполнен username/password и нет token — 3X-UI не сможет авторизоваться.")

        for label, path in (("base_url", ""), ("login_page", "/login")):
            try:
                resp = self._request("GET", path, allow_redirects=False)
                item = {"name": label, "method": "GET", "path": path or "/", **self._response_summary(resp, body_limit=300)}
                result["checks"].append(item)
            except Exception as exc:  # pragma: no cover - network dependent
                result["checks"].append({"name": label, "method": "GET", "path": path or "/", "error": str(exc)})

        login_success = False
        if self.cfg.username and self.cfg.password:
            # Clear cookies collected by GET checks so every login attempt is explicit.
            try:
                self.session.cookies.clear()
            except Exception:
                pass
            for mode, payload in (
                ("form", {"username": self.cfg.username, "password": self.cfg.password}),
                ("json", {"username": self.cfg.username, "password": self.cfg.password}),
            ):
                try:
                    kwargs = {"data" if mode == "form" else "json": payload}
                    resp = self._request("POST", "/login", **kwargs)
                    summary = self._response_summary(resp, body_limit=500)
                    data = summary.get("json")
                    success = bool((200 <= resp.status_code < 300 and self.session.cookies) or (isinstance(data, dict) and data.get("success") is True))
                    result["login_attempts"].append({"mode": mode, "path": "/login", "success": success, **summary})
                    if success:
                        login_success = True
                        break
                except Exception as exc:  # pragma: no cover - network dependent
                    result["login_attempts"].append({"mode": mode, "path": "/login", "success": False, "error": str(exc)})
        else:
            login_success = bool(self.cfg.token)

        if not login_success and not self.cfg.token:
            result["hints"].append("Login не прошёл. Если HTTP 403 — чаще всего неверный username/password, неверный WebBasePath или 3X-UI блокирует вход без API token.")
            result["success"] = False
            return result

        for path in ("/panel/api/inbounds/list", "/panel/inbound/list"):
            try:
                resp = self._request("GET", path)
                summary = self._response_summary(resp, body_limit=600)
                obj = summary.get("json")
                count = None
                if isinstance(obj, dict):
                    raw_obj = obj.get("obj") if "obj" in obj else obj
                    if isinstance(raw_obj, list):
                        count = len(raw_obj)
                elif isinstance(obj, list):
                    count = len(obj)
                result["inbound_attempts"].append({"path": path, "count": count, **summary})
                if 200 <= resp.status_code < 300 and count is not None:
                    result["success"] = True
                    result["inbounds_count"] = count
                    return result
            except Exception as exc:  # pragma: no cover - network dependent
                result["inbound_attempts"].append({"path": path, "error": str(exc)})

        result["success"] = False
        result["hints"].append("Login/token прошёл не полностью или inbounds API недоступен. Проверь порт 2053, WebBasePath, API token, и что 3X-UI версия поддерживает /panel/api/inbounds/list.")
        return result

    def get_inbound(self, inbound_id: int) -> Optional[Dict[str, Any]]:
        self.login()
        for path in (f"/panel/api/inbounds/get/{int(inbound_id)}", f"/panel/inbound/get/{int(inbound_id)}"):
            resp = self._request("GET", path)
            if resp.status_code == 404:
                continue
            if not (200 <= resp.status_code < 300):
                raise XUIError(f"get inbound {inbound_id} failed: HTTP {resp.status_code} {(resp.text or '')[:200]}")
            data = _safe_json(resp)
            if isinstance(data, dict):
                obj = data.get("obj") if "obj" in data else data
                if isinstance(obj, dict):
                    return obj
                if isinstance(obj, list):
                    return next((item for item in obj if int(item.get("id") or 0) == int(inbound_id)), None)
        # Fallback to list, useful for older panels.
        for item in self.list_inbounds():
            if int(item.get("id") or 0) == int(inbound_id):
                return item
        return None

    def list_inbounds(self) -> List[Dict[str, Any]]:
        self.login()
        for path in ("/panel/api/inbounds/list", "/panel/inbound/list"):
            resp = self._request("GET", path)
            if resp.status_code == 404:
                continue
            if not (200 <= resp.status_code < 300):
                raise XUIError(f"list inbounds failed: HTTP {resp.status_code} {(resp.text or '')[:200]}")
            data = _safe_json(resp)
            obj = data.get("obj") if isinstance(data, dict) else data
            if isinstance(obj, list):
                return [dict(item) for item in obj if isinstance(item, dict)]
        raise XUIError("list inbounds failed: no compatible endpoint")

    def add_client(self, inbound_id: int, client: Dict[str, Any]) -> Dict[str, Any]:
        self.login()
        body = {"id": int(inbound_id), "settings": json.dumps({"clients": [client]}, ensure_ascii=False)}
        errors: List[str] = []
        for path in ("/panel/api/inbounds/addClient", "/panel/inbound/addClient"):
            resp = self._request("POST", path, json=body)
            if resp.status_code == 404:
                continue
            if 200 <= resp.status_code < 300:
                data = _safe_json(resp)
                if isinstance(data, dict):
                    if data.get("success") is False:
                        errors.append(str(data.get("msg") or data)[:300])
                        continue
                    return data
                # Some 3X-UI versions have returned an empty successful response.
                return {"success": True, "empty_response": True, "status_code": resp.status_code}
            errors.append(f"{path}: HTTP {resp.status_code} {(resp.text or '')[:200]}")
        raise XUIError("add client failed: " + " | ".join(errors[-3:]))

    def delete_client(self, inbound_id: int, client_id: str) -> Dict[str, Any]:
        self.login()
        client_id = str(client_id or "").strip()
        errors: List[str] = []
        for path in (
            f"/panel/api/inbounds/{int(inbound_id)}/delClient/{client_id}",
            f"/panel/inbound/{int(inbound_id)}/delClient/{client_id}",
        ):
            resp = self._request("POST", path)
            if resp.status_code == 404:
                continue
            if 200 <= resp.status_code < 300:
                data = _safe_json(resp)
                if isinstance(data, dict):
                    if data.get("success") is False:
                        msg = str(data.get("msg") or "").lower()
                        if "not found" in msg or "no record" in msg:
                            return {"success": True, "not_found": True}
                        errors.append(str(data.get("msg") or data)[:300])
                        continue
                    return data
                return {"success": True, "empty_response": True, "status_code": resp.status_code}
            errors.append(f"{path}: HTTP {resp.status_code} {(resp.text or '')[:200]}")
        # If the client is already gone, a 404 means desired state is achieved.
        if errors and all("HTTP 404" in item for item in errors):
            return {"success": True, "not_found": True}
        raise XUIError("delete client failed: " + " | ".join(errors[-3:]))


def _safe_json(resp: requests.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return None


def _parse_settings(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            data = json.loads(value)
            return dict(data) if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def inbound_clients(inbound: Dict[str, Any]) -> List[Dict[str, Any]]:
    settings = _parse_settings(inbound.get("settings"))
    clients = settings.get("clients")
    if isinstance(clients, list):
        return [dict(item) for item in clients if isinstance(item, dict)]
    return []


def _client_identifier(client: Dict[str, Any]) -> str:
    for key in ("id", "password", "email"):
        value = str(client.get(key) or "").strip()
        if value:
            return value
    return ""


def client_email_prefix(default_prefix: str, location_payload: Optional[Dict[str, Any]] = None) -> str:
    payload = location_payload or {}
    prefix = str(payload.get("xui_client_email_prefix") or payload.get("client_email_prefix") or default_prefix or "inet:").strip()
    return prefix or "inet:"


def make_client_email(prefix: str, credential: Dict[str, Any]) -> str:
    location_code = str(credential.get("location_code") or "loc").strip().replace(" ", "_")
    user_id = int(credential.get("user_id") or 0)
    device_id = int(credential.get("device_id") or 0)
    # Keep the email deterministic and short. 3X-UI uses email as a unique label.
    return f"{prefix}u{user_id}:d{device_id}:{location_code}"[:120]


def make_client_sub_id(credential: Dict[str, Any], uuid_value: str) -> str:
    raw = f"inet:{credential.get('user_id')}:{credential.get('device_id')}:{credential.get('location_code')}:{uuid_value}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def make_vless_client(credential: Dict[str, Any], *, flow: str = "", email_prefix: str = "inet:") -> Dict[str, Any]:
    uuid_value = str(credential.get("uuid") or "").strip()
    telegram_id = str(credential.get("telegram_id") or "").strip()
    return {
        "id": uuid_value,
        "flow": str(flow or "").strip(),
        "email": make_client_email(email_prefix, credential),
        "limitIp": 0,
        "totalGB": 0,
        "expiryTime": 0,
        "enable": True,
        "tgId": telegram_id,
        "subId": make_client_sub_id(credential, uuid_value),
        "comment": f"inet device {credential.get('device_id')} {credential.get('device_name') or ''}"[:120],
        "reset": 0,
    }


def sync_inbound_managed_clients(
    api: XUIClient,
    *,
    inbound_id: int,
    desired_clients: List[Dict[str, Any]],
    email_prefix: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    inbound = api.get_inbound(inbound_id)
    if not inbound:
        raise XUIError(f"inbound {inbound_id} not found")
    current_clients = inbound_clients(inbound)
    managed_current = [item for item in current_clients if str(item.get("email") or "").startswith(email_prefix)]
    current_by_id = {_client_identifier(item): item for item in managed_current if _client_identifier(item)}
    desired_by_id = {_client_identifier(item): item for item in desired_clients if _client_identifier(item)}

    to_add = [client for cid, client in desired_by_id.items() if cid not in current_by_id]
    to_delete = [cid for cid in current_by_id.keys() if cid not in desired_by_id]

    result = {
        "inbound_id": int(inbound_id),
        "dry_run": bool(dry_run),
        "managed_current": len(managed_current),
        "desired": len(desired_by_id),
        "added": 0,
        "deleted": 0,
        "add_errors": [],
        "delete_errors": [],
    }

    if dry_run:
        # Dry-run is a successful connectivity/state calculation, not a failed sync.
        # The caller can safely use this for first setup: Test/Load inbounds, then
        # inspect would_add/would_delete before switching XUI_DRY_RUN=false.
        result["would_add"] = len(to_add)
        result["would_delete"] = len(to_delete)
        result["ok"] = True
        return result

    for client in to_add:
        try:
            api.add_client(inbound_id, client)
            result["added"] += 1
            time.sleep(0.05)
        except Exception as exc:  # pragma: no cover - network dependent
            result["add_errors"].append(str(exc)[:500])
    for client_id in to_delete:
        try:
            api.delete_client(inbound_id, client_id)
            result["deleted"] += 1
            time.sleep(0.05)
        except Exception as exc:  # pragma: no cover - network dependent
            result["delete_errors"].append(str(exc)[:500])

    result["ok"] = not result["add_errors"] and not result["delete_errors"]
    return result
