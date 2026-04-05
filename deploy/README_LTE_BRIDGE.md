# LTE bridge rollout (env-first)

Recommended flow:

1. App connects only to your VLESS bridge.
2. Bridge forwards traffic to the upstream mobile proxy provider.
3. Provider secrets stay only on the bridge server, never in app/backend client payloads.

## Best practice

- Keep bridge host/public settings in backend `vpn_payload`.
- Keep raw mobile provider host/port/login/password only in sing-box bridge config or bridge env.
- Keep location catalog in `DEFAULT_LOCATIONS_JSON` env override or builtin catalog so `ru-lte` / `uz-lte` are not disabled on restart.

## What is included in this bundle

- `sing-box/ru-lte-bridge.example.json`
- `sing-box/uz-lte-bridge.example.json`
- `env/.env.lte.example`
- admin panel modal for editing full `vpn_payload`
- RU/UZ LTE presets in admin panel

## Rollout order

1. Fill provider secrets on bridge server.
2. Generate UUID + REALITY key pair + short_id.
3. Put bridge connection data into admin location `vpn_payload`.
4. Test `/vpn/config/ru-lte`.
5. Confirm public IP is mobile RU/UZ.
