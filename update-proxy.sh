#!/bin/bash
cd "$(dirname "$0")"
echo " Updating SOCKS5 proxy..."
docker-compose down
docker build -t telegram-socks5:latest .
docker-compose up -d telegram-socks5
echo "Update completed"
echo "Check status: docker-compose ps" 