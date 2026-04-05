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


## ru-lte first rollout checklist

1. Add `ru-lte` to catalog (`BUILTIN_MVP_LOCATIONS_JSON` or `DEFAULT_LOCATIONS_JSON` env override).
2. Buy/select a mobile proxy provider for RU.
3. Deploy one bridge host for `ru-lte`.
4. Fill provider credentials only on the bridge sing-box config.
5. Put only bridge-facing VLESS values into admin `vpn_payload` for `ru-lte`.
6. Verify backend `/health` and `/vpn/config/ru-lte`.
7. Verify a user with an active subscription can receive the payload and connect.
8. Only after RU works, copy the same scheme for `uz-lte`.

## Outside this bundle

The following steps cannot be completed from the code bundle alone and require your infra/credentials:

- purchasing a mobile proxy provider
- provisioning the remote bridge VPS/server
- installing and starting sing-box on that remote host
- adding real provider login/password/upstream host to the bridge config
- testing external mobile IP from Android/iPhone against the live bridge
