#!/bin/bash
cd "$(dirname "$0")"
docker-compose up -d telegram-socks5
echo " SOCKS5 proxy started"
echo " Check status: docker-compose ps"
echo " View logs:   ./logs-proxy.sh" 