#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_mobile_payload(args: argparse.Namespace) -> dict:
    payload = {
        "engine": "nekobox",
        "protocol": "vless",
        "location_code": args.location_code,
        "remark": args.remark,
        "connect_mode": "tun",
        "full_tunnel": True,
        "server": args.server,
        "port": args.port,
        "uuid": args.uuid,
        "transport": args.transport,
        "network": args.transport,
        "security": "reality",
        "flow": args.flow,
        "sni": args.server_name,
        "server_name": args.server_name,
        "public_key": args.public_key,
        "short_id": args.short_id,
        "fingerprint": args.fingerprint,
        "packet_encoding": args.packet_encoding,
        "domain_resolver": args.domain_resolver,
        "dns_servers": args.dns_servers,
    }
    if args.transport == "grpc":
        payload["service_name"] = args.service_name
    if args.transport in {"ws", "websocket"}:
        payload["path"] = args.path
        if args.host:
            payload["host"] = args.host
    return payload


def build_bridge_config(args: argparse.Namespace) -> dict:
    outbound = {
        "type": args.provider_type,
        "tag": "mobile-upstream",
        "server": args.upstream_host,
        "server_port": args.upstream_port,
        "network": ["tcp", "udp"],
    }
    if args.provider_type == "socks":
        outbound["version"] = "5"
    if args.upstream_username:
        outbound["username"] = args.upstream_username
    if args.upstream_password:
        outbound["password"] = args.upstream_password

    inbound = {
        "type": "vless",
        "tag": "vless-in",
        "listen": "::",
        "listen_port": args.listen_port,
        "users": [{
            "name": f"{args.location_code}-user",
            "uuid": args.uuid,
            "flow": args.flow,
        }],
        "tls": {
            "enabled": True,
            "server_name": args.server_name,
            "reality": {
                "enabled": True,
                "handshake": {
                    "server": args.server_name,
                    "server_port": 443,
                },
                "private_key": args.private_key,
                "short_id": [args.short_id],
            },
        },
    }

    if args.transport == "grpc":
        inbound["transport"] = {"type": "grpc", "service_name": args.service_name}
    elif args.transport in {"ws", "websocket"}:
        transport = {"type": "ws", "path": args.path}
        if args.host:
            transport["headers"] = {"Host": args.host}
        inbound["transport"] = transport

    return {
        "log": {"level": "info"},
        "inbounds": [inbound],
        "outbounds": [outbound],
        "route": {"final": "mobile-upstream", "auto_detect_interface": True},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate both mobile vpn_payload for NekoBox and sing-box bridge config for a VLESS/REALITY location.")
    parser.add_argument('--location-code', required=True)
    parser.add_argument('--remark', required=True)
    parser.add_argument('--server', required=True, help='Public bridge host/IP the app connects to')
    parser.add_argument('--port', type=int, default=443, help='Public bridge port the app connects to')
    parser.add_argument('--listen-port', type=int, default=443, help='Inbound listen port on the bridge config')
    parser.add_argument('--uuid', required=True)
    parser.add_argument('--server-name', required=True, help='REALITY handshake server_name / SNI')
    parser.add_argument('--public-key', required=True)
    parser.add_argument('--private-key', required=True)
    parser.add_argument('--short-id', required=True)
    parser.add_argument('--transport', choices=['tcp', 'grpc', 'ws', 'websocket'], default='tcp')
    parser.add_argument('--service-name', default='grpc')
    parser.add_argument('--path', default='/')
    parser.add_argument('--host', default='')
    parser.add_argument('--flow', default='xtls-rprx-vision')
    parser.add_argument('--fingerprint', default='chrome')
    parser.add_argument('--packet-encoding', default='xudp')
    parser.add_argument('--domain-resolver', default='dns-remote')
    parser.add_argument('--dns', dest='dns_servers', action='append', default=None)
    parser.add_argument('--provider-type', choices=['socks', 'http'], default='socks')
    parser.add_argument('--upstream-host', required=True)
    parser.add_argument('--upstream-port', type=int, required=True)
    parser.add_argument('--upstream-username', default='')
    parser.add_argument('--upstream-password', default='')
    parser.add_argument('--output-dir', default='.')
    args = parser.parse_args()

    args.dns_servers = args.dns_servers or ['1.1.1.1', '8.8.8.8']
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    mobile = build_mobile_payload(args)
    bridge = build_bridge_config(args)

    mobile_path = output_dir / f'{args.location_code}.mobile-payload.json'
    bridge_path = output_dir / f'{args.location_code}.bridge.json'
    mobile_path.write_text(json.dumps(mobile, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    bridge_path.write_text(json.dumps(bridge, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print(json.dumps({
        'ok': True,
        'mobile_payload': str(mobile_path),
        'bridge_config': str(bridge_path),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
