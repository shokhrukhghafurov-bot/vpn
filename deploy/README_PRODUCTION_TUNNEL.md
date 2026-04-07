# Production tunnel bundle

This repo already serves `/vpn/config/{location_code}` and the mobile apps already expect a complete VLESS/REALITY payload.

## What this generator gives you

`generate_vless_reality_bundle.py` outputs two files from one source of truth:

- `<location>.mobile-payload.json` — paste into backend `vpn_payload` / admin location payload
- `<location>.bridge.json` — deploy on the sing-box bridge VPS

## Example

```bash
python deploy/generate_vless_reality_bundle.py   --location-code ru-lte   --remark "Russia LTE"   --server 203.0.113.10   --port 443   --listen-port 443   --uuid 11111111-2222-3333-4444-555555555555   --server-name www.cloudflare.com   --public-key REALITY_PUBLIC_KEY   --private-key REALITY_PRIVATE_KEY   --short-id abcd1234   --transport grpc   --service-name xyz   --upstream-host 10.0.0.2   --upstream-port 10000   --upstream-username provider_user   --upstream-password provider_pass   --output-dir deploy/out
```

## Final production sequence

1. Generate REALITY keypair on the bridge host.
2. Generate the pair of JSON files with the script above.
3. Deploy `<location>.bridge.json` to the VPS running sing-box.
4. Paste `<location>.mobile-payload.json` into the backend location `vpn_payload`.
5. Confirm admin diagnostics show both Android and iOS as `ready`.
6. Log in from the app and verify `/vpn/config/{location_code}` returns the same real values.
7. Test Android first, then iOS after `Libbox.xcframework` is built on macOS and linked into PacketTunnel.
