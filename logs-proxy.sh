#!/bin/bash
cd "$(dirname "$0")"
echo " SOCKS5 Proxy Logs (Press Ctrl+C to exit)"
echo "========================================"
docker-compose logs -f telegram-socks5 