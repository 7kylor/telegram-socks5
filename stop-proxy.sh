#!/bin/bash
cd "$(dirname "$0")"
docker-compose down
echo "SOCKS5 proxy stopped" 