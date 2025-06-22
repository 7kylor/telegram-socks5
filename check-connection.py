#!/usr/bin/env python3
"""
Simple connection checker and info display for Telegram SOCKS5 proxy
"""

import os
import socket
import subprocess
import sys

def get_server_ip():
    """Get the server's public IP address"""
    try:
        # Try multiple IP detection services
        import urllib.request
        for url in ['http://ifconfig.me/ip', 'http://ipinfo.io/ip', 'http://icanhazip.com']:
            try:
                with urllib.request.urlopen(url, timeout=5) as response:
                    ip = response.read().decode().strip()
                    if ip and '.' in ip and not ip.startswith(('192.168.', '10.', '172.')):
                        return ip
            except:
                continue
    except:
        pass
    
    # Fallback to hostname -I for local IP
    try:
        result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            ip = result.stdout.strip().split()[0]
            if ip and '.' in ip:
                return ip
    except:
        pass
    
    return 'YOUR_SERVER_IP'

def load_config():
    """Load configuration from proxy.env file"""
    config = {}
    config_file = "config/proxy.env"
    
    if os.path.exists(config_file):
        with open(config_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    
    return config

def check_port_connectivity(host, port):
    """Check if port is accessible"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except:
        return False

def main():
    """Main function to display connection info and check connectivity"""
    
    # Load configuration
    config = load_config()
    server_ip = get_server_ip()
    
    # Get the actual external ports (mapped ports)
    internal_proxy_port = int(config.get('PROXY_PORT', 1080))
    internal_metrics_port = int(config.get('METRICS_PORT', 8080))
    
    # Check if ports are auto-selected (1081/8082) or use config values
    if internal_proxy_port == 1080:
        proxy_port = 1081  # Auto-selected external port
    else:
        proxy_port = internal_proxy_port
        
    if internal_metrics_port == 8080:
        metrics_port = 8082  # Auto-selected external port
    else:
        metrics_port = internal_metrics_port
    
    admin_password = config.get('ADMIN_PASSWORD', 'admin_password_not_found')
    
    print("")
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║                    TELEGRAM SOCKET5 PROXY - CONNECTION INFO                   ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    print("")
    print(" YOUR PROXY CONNECTION DETAILS:")
    print("┌─────────────────────────────────────────────────────────────────────────────┐")
    print(f"│   Server IP: {server_ip}")
    print(f"│   Port: {proxy_port}")
    print(f"│   Username: admin")
    print(f"│   Password: {admin_password}")
    print(f"│   Protocol: SOCKET5/SOCKS5")
    print("└─────────────────────────────────────────────────────────────────────────────┘")
    print("")
    
    # Check connectivity
    print(" CONNECTION STATUS:")
    print("┌─────────────────────────────────────────────────────────────────────────────┐")
    
    # Check local port
    local_check = check_port_connectivity('localhost', proxy_port)
    print(f"│   Local Port {proxy_port}: {'✓ OPEN' if local_check else '✗ CLOSED'}")
    
    # Check metrics port
    metrics_check = check_port_connectivity('localhost', metrics_port)
    print(f"│   Metrics Port {metrics_port}: {'✓ OPEN' if metrics_check else '✗ CLOSED'}")
    
    print("└─────────────────────────────────────────────────────────────────────────────┘")
    print("")
    
    if local_check:
        print(" STATUS: ✓ PROXY IS RUNNING")
        print("")
        print(" TELEGRAM SETUP:")
        print(f"   1. Server: {server_ip}")
        print(f"   2. Port: {proxy_port}")
        print(f"   3. Username: admin")
        print(f"   4. Password: {admin_password}")
        print("")
        print(" QUICK CONNECTION STRING:")
        print(f"   socks5://admin:{admin_password}@{server_ip}:{proxy_port}")
        print("")
        print(" TELEGRAM DIRECT LINK (Click to add automatically):")
        print(f"   https://t.me/socks?server={server_ip}&port={proxy_port}&user=admin&pass={admin_password}")
        print("")
        print(" NEXT STEPS:")
        print("   1. Copy the connection details above")
        print("   2. Configure your Telegram app")
        print(f"   3. Test connection: python3 test-proxy.py --port {proxy_port}")
        print("")
    else:
        print(" STATUS: ✗ PROXY NOT ACCESSIBLE")
        print("")
        print(" TROUBLESHOOTING:")
        print("   1. Check container: docker ps")
        print("   2. Check logs: ./logs-proxy.sh")
        print("   3. Restart: ./stop-proxy.sh && ./start-proxy.sh")
        print("")
        sys.exit(1)

if __name__ == '__main__':
    main() 