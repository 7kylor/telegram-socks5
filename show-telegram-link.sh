#!/bin/bash

# Get current configuration
source config/proxy.env

# Get server IP
SERVER_IP=$(curl -4 -s --connect-timeout 5 http://ifconfig.me 2>/dev/null || \
            curl -4 -s --connect-timeout 5 http://ipinfo.io/ip 2>/dev/null || \
            curl -4 -s --connect-timeout 5 http://icanhazip.com 2>/dev/null || \
            echo "YOUR_SERVER_IP")

# Determine external port (auto-selected if internal is 1080)
if [[ "$PROXY_PORT" == "1080" ]]; then
    EXTERNAL_PORT=1081
else
    EXTERNAL_PORT=$PROXY_PORT
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                      TELEGRAM DIRECT LINK GENERATOR                          ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""
echo " CURRENT CONNECTION DETAILS:"
echo "┌─────────────────────────────────────────────────────────────────────────────┐"
echo "│   Server IP: $SERVER_IP"
echo "│   Port: $EXTERNAL_PORT"
echo "│   Username: admin"
echo "│   Password: $ADMIN_PASSWORD"
echo "│   Protocol: SOCKET5/SOCKS5"
echo "└─────────────────────────────────────────────────────────────────────────────┘"
echo ""
echo " TELEGRAM DIRECT LINK (Click to add proxy automatically):"
echo ""
echo "   https://t.me/socks?server=$SERVER_IP&port=$EXTERNAL_PORT&user=admin&pass=$ADMIN_PASSWORD"
echo ""
echo " INSTRUCTIONS:"
echo "   1. Copy the link above"
echo "   2. Open it in your browser or click it directly"
echo "   3. Telegram will automatically add the proxy settings"
echo "   4. No manual configuration needed!"
echo ""
echo " ALTERNATIVE MANUAL SETUP:"
echo "   Server: $SERVER_IP"
echo "   Port: $EXTERNAL_PORT"
echo "   Username: admin"
echo "   Password: $ADMIN_PASSWORD"
echo "" 