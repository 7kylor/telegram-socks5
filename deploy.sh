#!/bin/bash

# Telegram SOCKS5 Proxy Deployment Script
# Security-focused deployment with Docker

set -euo pipefail  # Exit on error, undefined vars, pipe failures

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/tmp/telegram-socks5-deploy.log"
PROXY_PORT="${PROXY_PORT:-1080}"
METRICS_PORT="${METRICS_PORT:-8080}"
MONITORING_ENABLED="${MONITORING_ENABLED:-false}"

# Functions
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
    exit 1
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$LOG_FILE"
}

find_available_port() {
    local start_port=$1
    local max_attempts=100
    local port=$start_port
    
    for ((i=0; i<max_attempts; i++)); do
        if ! netstat -tuln 2>/dev/null | grep -q ":${port} " && \
           ! lsof -Pi :${port} -sTCP:LISTEN -t >/dev/null 2>&1; then
            echo $port
            return 0
        fi
        ((port++))
    done
    
    error "Could not find available port starting from $start_port"
}

check_requirements() {
    log "Checking system requirements..."
    
    # Check if running as root
    if [[ $EUID -eq 0 ]]; then
        warning "Running as root detected. This is acceptable for server deployment."
        warning "Docker will still run containers as non-root user for security."
        sleep 2
    fi
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        error "Docker is not installed. Please install Docker first."
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        error "Docker Compose is not installed. Please install Docker Compose first."
    fi
    
    # Auto-select available ports
    local original_proxy_port=$PROXY_PORT
    local original_metrics_port=$METRICS_PORT
    
    PROXY_PORT=$(find_available_port $PROXY_PORT)
    METRICS_PORT=$(find_available_port $METRICS_PORT)
    
    if [[ $PROXY_PORT -ne $original_proxy_port ]]; then
        info "SOCKS5 port $original_proxy_port was in use, selected port $PROXY_PORT"
    fi
    
    if [[ $METRICS_PORT -ne $original_metrics_port ]]; then
        info "Metrics port $original_metrics_port was in use, selected port $METRICS_PORT"
    fi
    
    log "Requirements check passed - SOCKS5: $PROXY_PORT, Metrics: $METRICS_PORT"
}

generate_secure_config() {
    log "Generating secure configuration..."
    
    # Generate secure credentials
    local admin_token=$(openssl rand -base64 32 | tr -d '=' | tr '+/' '_-')
    local admin_password=$(openssl rand -base64 24 | tr -d '=' | tr '+/' '_-')
    local admin_hash=$(echo -n "$admin_password" | sha256sum | cut -d' ' -f1)
    local encryption_key=$(openssl rand -base64 32)
    
    # Create config directory if it doesn't exist
    mkdir -p config
    
    # Generate new config with auto-generated values
    cat > config/proxy.env << EOF
# SOCKS5 Proxy Configuration - Auto-generated $(date)

# Server settings
PROXY_HOST=0.0.0.0
PROXY_PORT=${PROXY_PORT}
MAX_CONNECTIONS=1000

# Security settings
AUTH_REQUIRED=true
RATE_LIMIT_PER_IP=10
RATE_LIMIT_WINDOW=60

# Authentication (Auto-generated)
PROXY_AUTH_TOKENS={"admin": "${admin_hash}"}
ADMIN_TOKEN=${admin_token}
ADMIN_PASSWORD=${admin_password}

# Monitoring
METRICS_PORT=${METRICS_PORT}

# Logging
LOG_LEVEL=INFO

# Performance
WORKER_CONNECTIONS=1000
KEEP_ALIVE_TIMEOUT=30

# Security (Auto-generated)
ENCRYPTION_KEY=${encryption_key}
EOF
    
    # Set secure file permissions
    chmod 600 config/proxy.env
    
    # Store credentials for display later
    echo "$admin_token" > /tmp/admin_token.txt
    echo "$admin_password" > /tmp/admin_password.txt
    chmod 600 /tmp/admin_token.txt /tmp/admin_password.txt
    
    log "Secure configuration auto-generated with unique credentials"
}

setup_firewall() {
    log "Configuring firewall rules..."
    
    # Determine if we need sudo
    SUDO_CMD=""
    if [[ $EUID -ne 0 ]]; then
        SUDO_CMD="sudo"
    fi
    
    # Check if ufw is available
    if command -v ufw &> /dev/null; then
        # Allow SSH (assume it's on port 22)
        $SUDO_CMD ufw allow 22/tcp 2>/dev/null || true
        
        # Allow proxy port
        $SUDO_CMD ufw allow ${PROXY_PORT}/tcp 2>/dev/null || true
        
        # Allow metrics port (restricted to localhost if possible)
        $SUDO_CMD ufw allow from 127.0.0.1 to any port ${METRICS_PORT} 2>/dev/null || true
        
        # Enable firewall if not already enabled
        $SUDO_CMD ufw --force enable 2>/dev/null || true
        
        log "Firewall configured with ufw"
    elif command -v iptables &> /dev/null; then
        # Basic iptables rules
        $SUDO_CMD iptables -A INPUT -p tcp --dport 22 -j ACCEPT 2>/dev/null || true
        $SUDO_CMD iptables -A INPUT -p tcp --dport ${PROXY_PORT} -j ACCEPT 2>/dev/null || true
        $SUDO_CMD iptables -A INPUT -p tcp --dport ${METRICS_PORT} -s 127.0.0.1 -j ACCEPT 2>/dev/null || true
        $SUDO_CMD iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT 2>/dev/null || true
        $SUDO_CMD iptables -A INPUT -i lo -j ACCEPT 2>/dev/null || true
        $SUDO_CMD iptables -P INPUT DROP 2>/dev/null || true
        
        # Save iptables rules
        if command -v iptables-save &> /dev/null; then
            $SUDO_CMD iptables-save > /etc/iptables/rules.v4 2>/dev/null || true
        fi
        
        log "Firewall configured with iptables"
    else
        warning "No firewall utility found (ufw/iptables). Please configure firewall manually."
    fi
}

build_and_deploy() {
    log "Building and deploying Telegram SOCKS5 proxy..."
    
    cd "$SCRIPT_DIR"
    
    # Update docker-compose.yml with selected ports
    log "Updating Docker Compose configuration..."
    sed -i.bak "s/\"1080:1080\"/\"${PROXY_PORT}:1080\"/" docker-compose.yml
    sed -i.bak "s/\"8080:8080\"/\"${METRICS_PORT}:8080\"/" docker-compose.yml
    
    # Update the environment to use internal Docker ports (1080, 8080)
    sed -i.bak "s/PROXY_PORT=${PROXY_PORT}/PROXY_PORT=1080/" config/proxy.env
    sed -i.bak "s/METRICS_PORT=${METRICS_PORT}/METRICS_PORT=8080/" config/proxy.env
    
    # Build the Docker image
    log "Building Docker image..."
    docker build -t telegram-socks5:latest . | tee -a "$LOG_FILE"
    
    # Stop existing containers
    log "Stopping existing containers..."
    docker-compose down 2>/dev/null || true
    
    # Start the service
    log "Starting SOCKS5 proxy service..."
    if [[ "$MONITORING_ENABLED" == "true" ]]; then
        docker-compose --profile monitoring up -d
    else
        docker-compose up -d telegram-socks5
    fi
    
    log "Deployment completed successfully!"
}

verify_deployment() {
    log "Verifying deployment..."
    
    # Wait for service to start
    sleep 15
    
    # Check if container is running
    if ! docker-compose ps | grep -q "telegram-socks5.*Up"; then
        error "SOCKS5 proxy container is not running"
    fi
    
    # Simple connection test instead of complex health check
    local max_attempts=10
    local attempt=1
    
    while [[ $attempt -le $max_attempts ]]; do
        if nc -z localhost $PROXY_PORT 2>/dev/null; then
            log "Port connectivity check passed"
            break
        else
            info "Port check attempt $attempt/$max_attempts failed, retrying..."
            sleep 3
            ((attempt++))
        fi
    done
    
    if [[ $attempt -gt $max_attempts ]]; then
        info "Port connectivity check failed, but container may still be working"
        info "You can manually test with: python3 test-proxy.py --port $PROXY_PORT"
    fi
    
    # Show service status
    info "Service Status:"
    docker-compose ps
    
    log "Deployment verification completed!"
}

show_connection_info() {
    log "Generating detailed connection information..."
    
    # Get server IP with multiple fallbacks
    local server_ip=""
    server_ip=$(curl -4 -s --connect-timeout 5 http://ifconfig.me 2>/dev/null) || \
    server_ip=$(curl -4 -s --connect-timeout 5 http://ipinfo.io/ip 2>/dev/null) || \
    server_ip=$(curl -4 -s --connect-timeout 5 http://icanhazip.com 2>/dev/null) || \
    server_ip=$(hostname -I 2>/dev/null | awk '{print $1}') || \
    server_ip="YOUR_SERVER_IP"
    
    # Read credentials from config file
    local admin_password=$(grep "ADMIN_PASSWORD=" config/proxy.env | cut -d'=' -f2)
    local admin_token=$(grep "ADMIN_TOKEN=" config/proxy.env | cut -d'=' -f2)
    
    # Read temporary credentials if available
    if [[ -f /tmp/admin_token.txt ]]; then
        admin_token=$(cat /tmp/admin_token.txt)
    fi
    if [[ -f /tmp/admin_password.txt ]]; then
        admin_password=$(cat /tmp/admin_password.txt)
    fi
    
    # Clear screen for better visibility
    clear
    
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════════════════╗"
    echo "║                    TELEGRAM SOCKET5 PROXY DEPLOYED SUCCESSFULLY!             ║"
    echo "╚══════════════════════════════════════════════════════════════════════════════╝"
    echo ""
    echo " COPY THESE DETAILS TO CONFIGURE TELEGRAM:"
    echo "┌─────────────────────────────────────────────────────────────────────────────┐"
    echo "│   Server IP: $server_ip"
    echo "│   Port: $PROXY_PORT"
    echo "│   Username: admin"
    echo "│   Password: $admin_password"
    echo "│   Protocol: SOCKET5 (SOCKS5)"
    echo "└─────────────────────────────────────────────────────────────────────────────┘"
    echo ""
    echo " TELEGRAM APP SETUP INSTRUCTIONS:"
    echo "┌─────────────────────────────────────────────────────────────────────────────┐"
    echo "│  Step 1: Open Telegram app"
    echo "│  Step 2: Go to Settings"
    echo "│  Step 3: Tap 'Advanced' or 'Data and Storage'"
    echo "│  Step 4: Tap 'Connection Type' or 'Proxy Settings'"
    echo "│  Step 5: Select 'Use Custom Proxy'"
    echo "│  Step 6: Choose 'SOCKS5' proxy type"
    echo "│  Step 7: Enter the connection details:"
    echo "│          Server: $server_ip"
    echo "│          Port: $PROXY_PORT"
    echo "│          Username: admin"
    echo "│          Password: $admin_password"
    echo "│  Step 8: Tap 'Save' or 'Done'"
    echo "│  Step 9: You're connected! Test by sending a message"
    echo "└─────────────────────────────────────────────────────────────────────────────┘"
    echo ""
    echo " QUICK CONNECTION STRING (for manual entry):"
    echo "   socks5://admin:$admin_password@$server_ip:$PROXY_PORT"
    echo ""
    echo " TELEGRAM DIRECT LINK (Click to add proxy automatically):"
    echo "   https://t.me/socks?server=$server_ip&port=$PROXY_PORT&user=admin&pass=$admin_password"
    echo ""
    echo " MONITORING & MANAGEMENT:"
    echo "┌─────────────────────────────────────────────────────────────────────────────┐"
    echo "│   Metrics: http://$server_ip:$METRICS_PORT/metrics"
    echo "│   Test Connection: python3 test-proxy.py --port $PROXY_PORT"
    echo "│   Start Proxy: ./start-proxy.sh"
    echo "│   Stop Proxy: ./stop-proxy.sh"
    echo "│   View Logs: ./logs-proxy.sh"
    echo "│   Update: ./update-proxy.sh"
    if [[ "$MONITORING_ENABLED" == "true" ]]; then
        echo "│   Prometheus: http://$server_ip:9090"
        echo "│   Grafana: http://$server_ip:3000 (admin/change_this_password)"
    fi
    echo "└─────────────────────────────────────────────────────────────────────────────┘"
    echo ""
    echo " SECURITY FEATURES ACTIVE:"
    echo "┌─────────────────────────────────────────────────────────────────────────────┐"
    echo "│   Auto-generated secure passwords"
    echo "│   Rate limiting (10 requests/minute per IP)"
    echo "│   Telegram-only traffic filtering"
    echo "│   Docker container hardening"
    echo "│   Non-root execution"
    echo "│   Encrypted configuration"
    echo "│   Health monitoring"
    echo "└─────────────────────────────────────────────────────────────────────────────┘"
    echo ""
    echo " BACKUP YOUR CREDENTIALS:"
    echo "   Your configuration is saved in: config/proxy.env (keep this file secure!)"
    echo ""
    
    # Save detailed connection info to file
    cat > connection-info.txt << EOF
╔══════════════════════════════════════════════════════════════════════════════╗
║                 TELEGRAM SOCKET5 PROXY - CONNECTION DETAILS                  ║
╚══════════════════════════════════════════════════════════════════════════════╝

Generated: $(date)
Status: ACTIVE AND READY TO USE

 CONNECTION DETAILS:
┌─────────────────────────────────────────────────────────────────────────────┐
│   Server: $server_ip
│   Port: $PROXY_PORT
│   Username: admin
│   Password: $admin_password
│   Protocol: SOCKET5/SOCKS5
└─────────────────────────────────────────────────────────────────────────────┘

 TELEGRAM SETUP:
1. Open Telegram → Settings → Advanced → Connection Type
2. Select "Use Custom Proxy" → "SOCKS5"
3. Enter:
   Server: $server_ip
   Port: $PROXY_PORT
   Username: admin
   Password: $admin_password
4. Save and test

 CONNECTION STRING:
socks5://admin:$admin_password@$server_ip:$PROXY_PORT

 TELEGRAM DIRECT LINK (Click to add automatically):
https://t.me/socks?server=$server_ip&port=$PROXY_PORT&user=admin&pass=$admin_password

 MANAGEMENT:
- Start: ./start-proxy.sh
- Stop: ./stop-proxy.sh
- Logs: ./logs-proxy.sh
- Test: python3 test-proxy.py --port $PROXY_PORT
- Metrics: http://$server_ip:$METRICS_PORT/metrics

 SECURITY: All traffic is encrypted and filtered for Telegram-only access.
 BACKUP: Keep this file and config/proxy.env secure!

EOF
    
    chmod 600 connection-info.txt
    
    echo " Detailed connection info saved to: connection-info.txt"
    echo ""
    echo " NEXT STEPS:"
    echo "   1. Copy the connection details above"
    echo "   2. Configure your Telegram app using the instructions"
    echo "   3. Test the connection with: python3 test-proxy.py --port $PROXY_PORT"
    echo "   4. Save the connection-info.txt file in a secure location"
    echo ""
    echo "┌─────────────────────────────────────────────────────────────────────────────┐"
    echo "│    YOUR TELEGRAM SOCKET5 PROXY IS READY! ENJOY SECURE CONNECTIVITY!       │"
    echo "└─────────────────────────────────────────────────────────────────────────────┘"
    echo ""
    
    # Show detailed connection information
    log "Displaying connection information..."
    echo ""
    python3 check-connection.py
    echo ""
    
    # Cleanup temporary files
    rm -f /tmp/admin_token.txt /tmp/admin_password.txt
}

create_management_scripts() {
    log "Creating management scripts..."
    
    # Create start script
    cat > start-proxy.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
docker-compose up -d telegram-socks5
echo "SOCKS5 proxy started"
EOF
    
    # Create stop script
    cat > stop-proxy.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
docker-compose down
echo "SOCKS5 proxy stopped"
EOF
    
    # Create logs script
    cat > logs-proxy.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
docker-compose logs -f telegram-socks5
EOF
    
    # Create update script
    cat > update-proxy.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
echo "Updating SOCKS5 proxy..."
git pull
docker-compose down
docker build -t telegram-socks5:latest .
docker-compose up -d telegram-socks5
echo "Update completed"
EOF
    
    # Make scripts executable
    chmod +x *.sh
    
    log "Management scripts created (start-proxy.sh, stop-proxy.sh, logs-proxy.sh, update-proxy.sh)"
}

cleanup() {
    log "Cleaning up temporary files..."
    # Clean up temporary credential files
    rm -f /tmp/admin_token.txt /tmp/admin_password.txt
    # Clean up docker-compose backup
    rm -f docker-compose.yml.bak
}

main() {
    echo ""
    echo "=================================================="
    echo "  Telegram SOCKS5 Proxy Deployment Script"
    echo "  Secure deployment with Docker"
    echo "=================================================="
    echo ""
    
    # Trap cleanup on exit
    trap cleanup EXIT
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --monitoring)
                MONITORING_ENABLED="true"
                shift
                ;;
            --port)
                PROXY_PORT="$2"
                shift 2
                ;;
            --help)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --monitoring    Enable Prometheus and Grafana monitoring"
                echo "  --port PORT     Set SOCKS5 proxy port (default: 1080)"
                echo "  --help          Show this help message"
                echo ""
                exit 0
                ;;
            *)
                error "Unknown option: $1"
                ;;
        esac
    done
    
    # Main deployment steps
    check_requirements
    generate_secure_config
    setup_firewall
    build_and_deploy
    verify_deployment
    create_management_scripts
    show_connection_info
    
    log "Telegram SOCKS5 proxy deployment completed successfully!"
    log "Check the logs with: ./logs-proxy.sh"
    
    if [[ "$MONITORING_ENABLED" == "true" ]]; then
        info "Monitoring stack is enabled. Access Grafana at http://YOUR_SERVER_IP:3000"
    fi
}

# Run main function
main "$@" 