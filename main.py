import asyncio
import os
import shutil
import subprocess
import logging

import uvicorn


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _log_level() -> str:
    return (os.getenv("LOG_LEVEL", "ERROR") or "ERROR").strip().lower()


def _print_probe_runtime() -> None:
    if not _env_bool("STARTUP_PROBE_LOG", False):
        return
    xray_bin = os.getenv("XRAY_BIN", "/usr/local/bin/xray")
    resolved = shutil.which("xray") or (xray_bin if os.path.isfile(xray_bin) else "missing")
    version = "missing"
    if resolved != "missing":
        try:
            out = subprocess.check_output([resolved, "version"], stderr=subprocess.STDOUT, timeout=8)
            version = (out.decode(errors="ignore").splitlines() or [""])[0].strip() or "ok"
        except Exception as exc:
            version = f"version_check_failed:{exc}"
    print(f"[vpn][probe-runtime] env_xray={xray_bin} resolved={resolved} version={version}", flush=True)


def main() -> None:
    logging.basicConfig(level=getattr(logging, _log_level().upper(), logging.ERROR))
    logging.getLogger("uvicorn.access").disabled = not _env_bool("UVICORN_ACCESS_LOG", False)
    _print_probe_runtime()
    target = os.getenv('RUN_TARGET', 'api').strip().lower()
    if target == 'api':
        uvicorn.run('backend:app', host='0.0.0.0', port=int(os.getenv('PORT', '3000')), log_level=_log_level(), access_log=_env_bool('UVICORN_ACCESS_LOG', False))
        return
    if target == 'bot':
        from bot import main as bot_main

        asyncio.run(bot_main())
        return
    raise RuntimeError("RUN_TARGET must be either 'api' or 'bot'")


if __name__ == '__main__':
    main()
