"""3X-UI client sync helpers.

The backend DB remains the source of truth. 3X-UI is treated as the runtime
Xray control plane: managed clients are added/removed from selected inbounds so
old raw VLESS links stop working after a device is deleted.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin

import requests

logger = logging.getLogger("inet.vpn.xui")


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
            self.session.headers.update({"Authorization": f"Bearer {cfg.token}"})
        self.session.headers.update({"User-Agent": "inet-vpn-backend/xui-sync"})

    def _url(self, path: str) -> str:
        base = str(self.cfg.base_url or "").strip().rstrip("/") + "/"
        return urljoin(base, path.lstrip("/"))

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", max(1, int(self.cfg.timeout_sec or 8)))
        kwargs.setdefault("verify", bool(self.cfg.verify_ssl))
        resp = self.session.request(method.upper(), self._url(path), **kwargs)
        return resp

    def login(self) -> None:
        if self.cfg.token:
            return
        if not self.cfg.username or not self.cfg.password:
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
        raise XUIError(f"3X-UI login failed for {self.cfg.key}: {last_error}")

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
        result["would_add"] = len(to_add)
        result["would_delete"] = len(to_delete)
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
