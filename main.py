import asyncio
import os
import shutil
import subprocess

import uvicorn

from config import settings


def _print_probe_runtime() -> None:
    xray_bin = os.getenv("XRAY_BIN", "/usr/local/bin/xray")
    resolved = shutil.which("xray") or (xray_bin if os.path.isfile(xray_bin) else "missing")
    version = "missing"
    if resolved != "missing":
        try:
            out = subprocess.check_output([resolved, "version"], stderr=subprocess.STDOUT, timeout=8)
            version = (out.decode(errors="ignore").splitlines() or [""])[0].strip() or "ok"
        except Exception as exc:
            version = f"version_check_failed:{exc}"
    if os.getenv("VPN_PRINT_PROBE_RUNTIME", "0").strip().lower() in {"1", "true", "yes", "on"}:
        print(f"[vpn][probe-runtime] env_xray={xray_bin} resolved={resolved} version={version}", flush=True)


def main() -> None:
    _print_probe_runtime()
    target = os.getenv('RUN_TARGET', 'api').strip().lower()
    if target == 'api':
        uvicorn.run(
            'backend:app',
            host='0.0.0.0',
            port=int(os.getenv('PORT', '3000')),
            log_level=getattr(settings, 'UVICORN_LOG_LEVEL', 'error'),
            access_log=bool(getattr(settings, 'UVICORN_ACCESS_LOG', False)),
        )
        return
    if target == 'bot':
        from bot import main as bot_main

        asyncio.run(bot_main())
        return
    raise RuntimeError("RUN_TARGET must be either 'api' or 'bot'")


if __name__ == '__main__':
    main()
