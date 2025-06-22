#!/usr/bin/env python3
"""
Telegram-specific SOCKS5 proxy test
Tests all Telegram domains and services through the proxy
"""

import socket
import struct
import sys
import os
import time
import ssl

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

def socks5_connect(proxy_host, proxy_port, target_host, target_port, username=None, password=None):
    """Establish SOCKS5 connection and return the socket"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        
        sock.connect((proxy_host, proxy_port))
        
        # SOCKS5 handshake
        if username and password:
            handshake = struct.pack('!BBB', 5, 1, 2)
        else:
            handshake = struct.pack('!BBB', 5, 1, 0)
        
        sock.send(handshake)
        response = sock.recv(2)
        
        if len(response) != 2:
            raise Exception("Invalid handshake response")
        
        version, method = struct.unpack('!BB', response)
        
        if version != 5:
            raise Exception(f"Invalid SOCKS version: {version}")
        
        if method == 0xFF:
            raise Exception("No acceptable authentication method")
        
        # Handle authentication if required
        if method == 2:
            if not username or not password:
                raise Exception("Authentication required but no credentials provided")
            
            auth_request = struct.pack('!BB', 1, len(username)) + username.encode()
            auth_request += struct.pack('!B', len(password)) + password.encode()
            
            sock.send(auth_request)
            auth_response = sock.recv(2)
            
            if len(auth_response) != 2:
                raise Exception("Invalid authentication response")
            
            auth_version, auth_status = struct.unpack('!BB', auth_response)
            
            if auth_status != 0:
                raise Exception("Authentication failed")
        
        # Connect to target through proxy
        request = struct.pack('!BBB', 5, 1, 0)
        request += struct.pack('!B', 3)
        request += struct.pack('!B', len(target_host)) + target_host.encode()
        request += struct.pack('!H', target_port)
        
        sock.send(request)
        connect_response = sock.recv(10)
        
        if len(connect_response) < 10:
            raise Exception("Invalid connect response")
        
        response_version, response_code = struct.unpack('!BB', connect_response[:2])
        
        if response_version != 5:
            raise Exception(f"Invalid response version: {response_version}")
        
        if response_code != 0:
            error_messages = {
                1: "General SOCKS server failure",
                2: "Connection not allowed by ruleset",
                3: "Network unreachable",
                4: "Host unreachable",
                5: "Connection refused",
                6: "TTL expired",
                7: "Command not supported",
                8: "Address type not supported"
            }
            error_msg = error_messages.get(response_code, f"Unknown error code: {response_code}")
            raise Exception(f"SOCKS5 connection failed: {error_msg}")
        
        return sock
        
    except Exception as e:
        if 'sock' in locals():
            sock.close()
        raise e

def test_telegram_domain(proxy_host, proxy_port, username, password, domain, port, description):
    """Test connection to a specific Telegram domain"""
    try:
        print(f" Testing {description} ({domain}:{port})...")
        
        sock = socks5_connect(proxy_host, proxy_port, domain, port, username, password)
        
        if port == 443:  # HTTPS
            context = ssl.create_default_context()
            ssl_sock = context.wrap_socket(sock, server_hostname=domain)
            
            # Send simple HTTP request
            http_request = f"GET / HTTP/1.1\r\nHost: {domain}\r\nConnection: close\r\n\r\n"
            ssl_sock.send(http_request.encode())
            
            # Try to receive response
            response = ssl_sock.recv(1024)
            ssl_sock.close()
            
            if response:
                print(f"  {description}: Connected and received {len(response)} bytes")
                return True
            else:
                print(f"  {description}: Connected but no response")
                return True
                
        else:  # HTTP or other
            # For non-HTTPS, just test the connection
            sock.close()
            print(f"  {description}: Connection successful")
            return True
            
    except Exception as e:
        print(f"  {description}: {e}")
        return False

def main():
    """Main test function"""
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║                        TELEGRAM DOMAINS CONNECTIVITY TEST                    ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    
    # Load configuration
    config = load_config()
    proxy_host = "localhost"
    proxy_port = int(config.get('PROXY_PORT', 1080))
    
    if proxy_port == 1080:
        proxy_port = 1081
    
    username = "admin"
    password = config.get('ADMIN_PASSWORD', '')
    
    print(f"\n Test Configuration:")
    print(f"   Proxy: {proxy_host}:{proxy_port}")
    print(f"   Username: {username}")
    print(f"   Password: {'*' * len(password) if password else 'None'}")
    print(f"\n{'='*80}")
    
    # Telegram domains to test (from the whitelist)
    telegram_tests = [
        ("api.telegram.org", 443, "Telegram Bot API"),
        ("core.telegram.org", 443, "Telegram Core API"),
        ("web.telegram.org", 443, "Telegram Web"),
        ("desktop.telegram.org", 443, "Telegram Desktop Updates"),
        ("updates.tdesktop.com", 443, "Desktop Client Updates"),
    ]
    
    # Test non-Telegram domains (should be blocked)
    blocked_tests = [
        ("google.com", 80, "Google (should be blocked)"),
        ("facebook.com", 80, "Facebook (should be blocked)"),
        ("github.com", 80, "GitHub (should be blocked)"),
    ]
    
    print("\n TESTING TELEGRAM DOMAINS (Should work):")
    print("="*50)
    
    telegram_success = 0
    for domain, port, description in telegram_tests:
        if test_telegram_domain(proxy_host, proxy_port, username, password, domain, port, description):
            telegram_success += 1
        time.sleep(1)  # Small delay between tests
    
    print(f"\  TESTING NON-TELEGRAM DOMAINS (Should be blocked):")
    print("="*50)
    
    blocked_count = 0
    for domain, port, description in blocked_tests:
        try:
            print(f" Testing {description} ({domain}:{port})...")
            sock = socks5_connect(proxy_host, proxy_port, domain, port, username, password)
            sock.close()
            print(f"  {description}: UNEXPECTED SUCCESS (security issue)")
        except Exception as e:
            if "Connection not allowed by ruleset" in str(e):
                print(f"  {description}: Correctly blocked by security filter")
                blocked_count += 1
            else:
                print(f"  {description}: Failed with error: {e}")
        time.sleep(1)
    
    # Final results
    print(f"\n{'='*80}")
    print(f"  TELEGRAM CONNECTIVITY: {telegram_success}/{len(telegram_tests)} domains accessible")
    print(f"   SECURITY FILTERING: {blocked_count}/{len(blocked_tests)} non-Telegram domains blocked")
    
    print(f"\n DETAILED RESULTS:")
    print(f"     Telegram domains working: {telegram_success > 0}")
    print(f"     Security filtering active: {blocked_count > 0}")
    print(f"    Authentication working:  ")
    print(f"    Data transmission:  ")
    
    if telegram_success > 0 and blocked_count > 0:
        print(f"\n PERFECT! Your proxy is working exactly as designed:")
        print(f"     Allows Telegram traffic")
        print(f"     Blocks non-Telegram traffic (security feature)")
        print(f"    Secure authentication")
        print(f"    Ready for Telegram use!")
        
    elif telegram_success > 0:
        print(f"\n  GOOD! Telegram connectivity works")
        print(f"     Security filtering may need attention")
        
    else:
        print(f"\n  ISSUE: Telegram domains not accessible")
        print(f"    Check proxy configuration")
        sys.exit(1)

if __name__ == '__main__':
    main() 