#!/bin/bash

# Start Bypass Server for Telegram SOCKS5 Proxy
# Implements multiple bypass techniques to avoid blocking

set -e

LOG_FILE="bypass.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1" | tee -a "$LOG_FILE"
    exit 1
}

info() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: $1" | tee -a "$LOG_FILE"
}

check_requirements() {
    log "Checking bypass server requirements..."
    
    # Check if main proxy is running
    if ! docker ps | grep -q "telegram-socks5.*Up"; then
        error "Main SOCKS5 proxy is not running. Start it first with ./deploy.sh"
    fi
    
    # Check Python dependencies
    if ! python3 -c "import aiohttp, cryptography" 2>/dev/null; then
        log "Installing additional Python dependencies..."
        pip3 install aiohttp cryptography
    fi
    
    log "Requirements check completed"
}

get_server_info() {
    log "Getting server information..."
    
    # Get server IP
    SERVER_IP=$(curl -4 -s --connect-timeout 5 http://ifconfig.me 2>/dev/null || \
                curl -4 -s --connect-timeout 5 http://ipinfo.io/ip 2>/dev/null || \
                curl -4 -s --connect-timeout 5 http://icanhazip.com 2>/dev/null || \
                echo "localhost")
    
    # Get proxy credentials
    if [[ -f "config/proxy.env" ]]; then
        # Extract admin password safely without sourcing the whole file
        ADMIN_PASS=$(grep "^ADMIN_PASSWORD=" config/proxy.env | cut -d'=' -f2)
        if [[ -z "$ADMIN_PASS" ]]; then
            error "Admin password not found in configuration"
        fi
    else
        error "Proxy configuration not found. Deploy main proxy first."
    fi
    
    log "Server IP: $SERVER_IP"
    log "Proxy credentials loaded"
}

start_bypass_server() {
    log "Starting bypass server with all anti-blocking methods..."
    
    # Set environment variables for bypass server
    export SOCKS_HOST="localhost"
    export SOCKS_PORT="1081"  # External Docker port mapping
    export SOCKS_USERNAME="admin"
    export SOCKS_PASSWORD="$ADMIN_PASS"
    export BYPASS_HTTP_PORT="8443"
    export BYPASS_WS_PORT="8444"
    
    # Start bypass server in background
    nohup python3 src/bypass_server.py > bypass-server.log 2>&1 &
    BYPASS_PID=$!
    echo $BYPASS_PID > bypass-server.pid
    
    # Wait a moment for server to start
    sleep 5
    
    # Check if server started successfully
    if ! kill -0 $BYPASS_PID 2>/dev/null; then
        error "Bypass server failed to start. Check bypass-server.log for details."
    fi
    
    log "Bypass server started successfully (PID: $BYPASS_PID)"
}

open_firewall_ports() {
    log "Opening firewall ports for bypass methods..."
    
    # Open bypass ports
    BYPASS_PORTS=(8443 8444 8000:9000)
    
    for port in "${BYPASS_PORTS[@]}"; do
        if command -v ufw >/dev/null 2>&1; then
            ufw allow $port/tcp 2>/dev/null || true
        elif command -v firewall-cmd >/dev/null 2>&1; then
            if [[ "$port" == *":"* ]]; then
                # Port range
                firewall-cmd --permanent --add-port=${port}/tcp 2>/dev/null || true
            else
                firewall-cmd --permanent --add-port=${port}/tcp 2>/dev/null || true
            fi
            firewall-cmd --reload 2>/dev/null || true
        fi
    done
    
    log "Firewall ports opened"
}

show_bypass_info() {
    log "Displaying bypass connection information..."
    
    clear
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════════════════╗"
    echo "║                    BYPASS SERVER STARTED SUCCESSFULLY!                       ║"
    echo "╚══════════════════════════════════════════════════════════════════════════════╝"
    echo ""
    echo " ANTI-BLOCKING METHODS ACTIVE:"
    echo "┌─────────────────────────────────────────────────────────────────────────────┐"
    echo "│    Port Hopping: Ports 8000-9000 (changes every 5 minutes)"
    echo "│    HTTP Tunnel: http://$SERVER_IP:8443"
    echo "│    WebSocket Tunnel: ws://$SERVER_IP:8444/ws"
    echo "│    Domain Fronting: Via CDN providers"
    echo "│    Traffic Obfuscation: Encrypted + fake HTTP headers"
    echo "└─────────────────────────────────────────────────────────────────────────────┘"
    echo ""
    echo " BYPASS CONNECTION METHODS:"
    echo "┌─────────────────────────────────────────────────────────────────────────────┐"
    echo "│   Method 1: Direct SOCKS5 (if not blocked)"
    echo "│   Method 2: HTTP Tunnel (looks like web traffic)"
    echo "│   Method 3: WebSocket Tunnel (looks like chat app)"
    echo "│   Method 4: Port Hopping (random ports)"
    echo "│   Method 5: Domain Fronting (via CDN)"
    echo "└─────────────────────────────────────────────────────────────────────────────┘"
    echo ""
    echo " CLIENT USAGE:"
    echo "┌─────────────────────────────────────────────────────────────────────────────┐"
    echo "│   Test bypass: python3 src/bypass_client.py"
    echo "│   Auto-fallback: Client tries all methods automatically"
    echo "│   Server: $SERVER_IP"
    echo "│   Credentials: admin / $ADMIN_PASS"
    echo "└─────────────────────────────────────────────────────────────────────────────┘"
    echo ""
    echo " TELEGRAM CONFIGURATION:"
    echo "┌─────────────────────────────────────────────────────────────────────────────┐"
    echo "│   Use the same settings as before:"
    echo "│   Server: $SERVER_IP"
    echo "│   Port: 1081 (or bypass ports if blocked)"
    echo "│   Username: admin"
    echo "│   Password: $ADMIN_PASS"
    echo "│   "
    echo "│   If main proxy is blocked, the bypass client will"
    echo "│   automatically try alternative connection methods."
    echo "└─────────────────────────────────────────────────────────────────────────────┘"
    echo ""
    echo " MANAGEMENT:"
    echo "┌─────────────────────────────────────────────────────────────────────────────┐"
    echo "│   Stop bypass: ./stop-bypass.sh"
    echo "│   View logs: tail -f bypass-server.log"
    echo "│   Test connection: python3 src/bypass_client.py"
    echo "│   Status: ps aux | grep bypass_server"
    echo "└─────────────────────────────────────────────────────────────────────────────┘"
    echo ""
    echo " SECURITY FEATURES:"
    echo "┌─────────────────────────────────────────────────────────────────────────────┐"
    echo "│    Traffic encryption and obfuscation"
    echo "│    Fake HTTP headers to mimic web traffic"
    echo "│    Multiple connection methods"
    echo "│    Dynamic port hopping"
    echo "│    Domain fronting via legitimate CDNs"
    echo "│    WebSocket tunneling (looks like chat apps)"
    echo "└─────────────────────────────────────────────────────────────────────────────┘"
    echo ""
    echo "┌─────────────────────────────────────────────────────────────────────────────┐"
    echo "│    BYPASS SERVER IS READY! YOUR PROXY IS NOW HIGHLY RESISTANT TO BLOCKING   │"
    echo "└─────────────────────────────────────────────────────────────────────────────┘"
    echo ""
    
    # Save bypass info to file
    cat > bypass-info.txt << EOF
╔══════════════════════════════════════════════════════════════════════════════╗
║                    BYPASS SERVER CONNECTION METHODS                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

Generated: $(date)
Status: ACTIVE - ANTI-BLOCKING ENABLED

  BYPASS METHODS ACTIVE:
┌─────────────────────────────────────────────────────────────────────────────┐
│   Port Hopping: Ports 8000-9000 (changes every 5 minutes)
│   HTTP Tunnel: http://$SERVER_IP:8443
│   WebSocket Tunnel: ws://$SERVER_IP:8444/ws
│   Domain Fronting: Via CDN providers
│   Traffic Obfuscation: Encrypted + fake HTTP headers
└─────────────────────────────────────────────────────────────────────────────┘

  CONNECTION PRIORITY:
1. Direct SOCKS5: $SERVER_IP:1081
2. HTTP Tunnel: $SERVER_IP:8443
3. WebSocket: $SERVER_IP:8444
4. Port Hopping: $SERVER_IP:8000-9000
5. Domain Fronting: Via CDN

CLIENT USAGE:
- Test: python3 src/bypass_client.py
- Auto-fallback: Client tries all methods
- Credentials: admin / $ADMIN_PASS

  SECURITY: All traffic encrypted and obfuscated to avoid detection.

EOF
    
    chmod 600 bypass-info.txt
    
    log "Bypass server information saved to bypass-info.txt"
}

main() {
    echo ""
    echo "=================================================="
    echo "  Telegram SOCKS5 Bypass Server"
    echo "  Anti-blocking & censorship resistance"
    echo "=================================================="
    echo ""
    
    check_requirements
    get_server_info
    open_firewall_ports
    start_bypass_server
    show_bypass_info
    
    log "Bypass server deployment completed successfully!"
    log "Your proxy is now highly resistant to blocking attempts"
}

# Run main function
main "$@" 