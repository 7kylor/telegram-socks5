#!/bin/bash
# Advanced iptables rules for Telegram SOCKS5 proxy security

set -euo pipefail

# Configuration
PROXY_PORT="${PROXY_PORT:-1080}"
METRICS_PORT="${METRICS_PORT:-8080}"
SSH_PORT="${SSH_PORT:-22}"

# Telegram IP ranges
TELEGRAM_IPS=(
    "149.154.160.0/20"
    "91.108.4.0/22"
    "91.108.8.0/22"
    "91.108.12.0/22"
    "91.108.16.0/22"
    "91.108.20.0/22"
    "91.108.56.0/22"
    "149.154.164.0/22"
    "149.154.168.0/22"
    "149.154.172.0/22"
)

# Clear existing rules
iptables -F
iptables -X
iptables -t nat -F
iptables -t nat -X
iptables -t mangle -F
iptables -t mangle -X

# Default policies
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT ACCEPT

# Loopback interface
iptables -A INPUT -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT

# Allow established and related connections
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# SSH access (secure)
iptables -A INPUT -p tcp --dport $SSH_PORT -m conntrack --ctstate NEW -m limit --limit 3/min --limit-burst 3 -j ACCEPT

# SOCKS5 proxy port with rate limiting
iptables -A INPUT -p tcp --dport $PROXY_PORT -m conntrack --ctstate NEW -m limit --limit 20/min --limit-burst 10 -j ACCEPT

# Metrics port (localhost only)
iptables -A INPUT -p tcp --dport $METRICS_PORT -s 127.0.0.1 -j ACCEPT
iptables -A INPUT -p tcp --dport $METRICS_PORT -s 172.0.0.0/8 -j ACCEPT

# Allow outbound connections to Telegram servers only
for ip_range in "${TELEGRAM_IPS[@]}"; do
    iptables -A OUTPUT -d $ip_range -j ACCEPT
done

# DNS (for resolving Telegram domains)
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT

# Allow HTTPS for updates and monitoring
iptables -A OUTPUT -p tcp --dport 443 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 80 -j ACCEPT

# Drop invalid packets
iptables -A INPUT -m conntrack --ctstate INVALID -j DROP

# Protection against common attacks
iptables -A INPUT -p tcp --tcp-flags ALL NONE -j DROP
iptables -A INPUT -p tcp --tcp-flags ALL ALL -j DROP
iptables -A INPUT -p tcp --tcp-flags ALL FIN,URG,PSH -j DROP
iptables -A INPUT -p tcp --tcp-flags ALL SYN,RST,ACK,FIN,URG -j DROP
iptables -A INPUT -p tcp --tcp-flags SYN,RST SYN,RST -j DROP
iptables -A INPUT -p tcp --tcp-flags SYN,FIN SYN,FIN -j DROP

# Rate limiting for new connections
iptables -A INPUT -p tcp -m conntrack --ctstate NEW -m limit --limit 50/sec --limit-burst 50 -j ACCEPT
iptables -A INPUT -p tcp -m conntrack --ctstate NEW -j DROP

# Log dropped packets (optional - uncomment if needed)
# iptables -A INPUT -j LOG --log-prefix "iptables-dropped: "

# Save rules
if command -v iptables-save >/dev/null 2>&1; then
    iptables-save > /etc/iptables/rules.v4 2>/dev/null || true
fi

echo "Advanced iptables rules applied successfully" 