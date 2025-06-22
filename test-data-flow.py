#!/usr/bin/env python3
"""
Comprehensive SOCKS5 proxy data flow test
Tests actual data transmission through the proxy
"""

import socket
import struct
import sys
import os
import time
import threading
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
        # Create socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        
        print(f" Connecting to SOCKS5 proxy at {proxy_host}:{proxy_port}...")
        sock.connect((proxy_host, proxy_port))
        
        # SOCKS5 handshake
        if username and password:
            handshake = struct.pack('!BBB', 5, 1, 2)  # Version 5, 1 method, username/password
        else:
            handshake = struct.pack('!BBB', 5, 1, 0)  # Version 5, 1 method, no auth
        
        sock.send(handshake)
        response = sock.recv(2)
        
        if len(response) != 2:
            raise Exception("Invalid handshake response")
        
        version, method = struct.unpack('!BB', response)
        
        if version != 5:
            raise Exception(f"Invalid SOCKS version: {version}")
        
        if method == 0xFF:
            raise Exception("No acceptable authentication method")
        
        print(f" SOCKS5 handshake successful (method: {method})")
        
        # Handle authentication if required
        if method == 2:  # Username/password authentication
            if not username or not password:
                raise Exception("Authentication required but no credentials provided")
            
            print(" Performing authentication...")
            auth_request = struct.pack('!BB', 1, len(username)) + username.encode()
            auth_request += struct.pack('!B', len(password)) + password.encode()
            
            sock.send(auth_request)
            auth_response = sock.recv(2)
            
            if len(auth_response) != 2:
                raise Exception("Invalid authentication response")
            
            auth_version, auth_status = struct.unpack('!BB', auth_response)
            
            if auth_status != 0:
                raise Exception("Authentication failed")
            
            print(" Authentication successful")
        
        # Connect to target through proxy
        print(f" Connecting to {target_host}:{target_port} through proxy...")
        
        # SOCKS5 connect request
        request = struct.pack('!BBB', 5, 1, 0)  # Version, connect, reserved
        request += struct.pack('!B', 3)  # Domain name type
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
        
        print(f" Successfully connected to {target_host}:{target_port}")
        return sock
        
    except Exception as e:
        if 'sock' in locals():
            sock.close()
        raise e

def test_http_request(sock, host, path="/"):
    """Send HTTP request and receive response through SOCKS5"""
    try:
        # Send HTTP GET request
        http_request = f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\nUser-Agent: SOCKS5-Test/1.0\r\n\r\n"
        
        print(f" Sending HTTP request to {host}{path}...")
        sock.send(http_request.encode())
        
        # Receive response
        print("📥 Receiving response...")
        response = b""
        start_time = time.time()
        
        while True:
            try:
                data = sock.recv(4096)
                if not data:
                    break
                response += data
                
                # Timeout after 10 seconds
                if time.time() - start_time > 10:
                    break
                    
            except socket.timeout:
                break
        
        if response:
            response_str = response.decode('utf-8', errors='ignore')
            lines = response_str.split('\n')
            status_line = lines[0] if lines else "No response"
            
            print(f" Received response: {status_line.strip()}")
            print(f" Data received: {len(response)} bytes")
            
            # Look for common HTTP status codes
            if "200 OK" in status_line:
                print(" HTTP 200 OK - Request successful")
                return True
            elif "301" in status_line or "302" in status_line:
                print(" HTTP Redirect - Request successful")
                return True
            elif "403" in status_line:
                print(" HTTP 403 Forbidden - Connection working but access denied")
                return True
            else:
                print(f" HTTP Response: {status_line.strip()}")
                return True
        else:
            print(" No response received")
            return False
            
    except Exception as e:
        print(f" HTTP request failed: {e}")
        return False

def test_telegram_api(proxy_host, proxy_port, username, password):
    """Test actual Telegram API access through proxy"""
    print("\n Testing Telegram API access...")
    
    try:
        # Connect to Telegram API
        sock = socks5_connect(proxy_host, proxy_port, "api.telegram.org", 443, username, password)
        
        # Wrap in SSL
        print(" Establishing SSL connection...")
        context = ssl.create_default_context()
        ssl_sock = context.wrap_socket(sock, server_hostname="api.telegram.org")
        
        # Test HTTP request to Telegram API
        success = test_http_request(ssl_sock, "api.telegram.org", "/")
        
        ssl_sock.close()
        return success
        
    except Exception as e:
        print(f" Telegram API test failed: {e}")
        return False

def test_web_access(proxy_host, proxy_port, username, password):
    """Test general web access through proxy"""
    print("\n Testing general web access...")
    
    test_sites = [
        ("httpbin.org", 80, "/ip"),
        ("ifconfig.me", 80, "/"),
    ]
    
    success_count = 0
    
    for host, port, path in test_sites:
        try:
            print(f"\n Testing {host}{path}...")
            sock = socks5_connect(proxy_host, proxy_port, host, port, username, password)
            
            if test_http_request(sock, host, path):
                success_count += 1
                print(f" {host} test successful")
            else:
                print(f" {host} test failed")
            
            sock.close()
            
        except Exception as e:
            print(f" {host} test failed: {e}")
    
    return success_count > 0

def test_data_throughput(proxy_host, proxy_port, username, password):
    """Test data throughput through proxy"""
    print("\n Testing data throughput...")
    
    try:
        # Connect to a site that returns JSON data
        sock = socks5_connect(proxy_host, proxy_port, "httpbin.org", 80, username, password)
        
        # Request JSON data
        start_time = time.time()
        success = test_http_request(sock, "httpbin.org", "/json")
        end_time = time.time()
        
        if success:
            duration = end_time - start_time
            print(f" Request completed in {duration:.2f} seconds")
            print(" Data throughput test successful")
        
        sock.close()
        return success
        
    except Exception as e:
        print(f" Throughput test failed: {e}")
        return False

def main():
    """Main test function"""
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║                     COMPREHENSIVE SOCKS5 DATA FLOW TEST                      ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    
    # Load configuration
    config = load_config()
    proxy_host = "localhost"
    proxy_port = int(config.get('PROXY_PORT', 1080))
    
    # Check if ports are auto-selected
    if proxy_port == 1080:
        proxy_port = 1081  # Auto-selected external port
    
    username = "admin"
    password = config.get('ADMIN_PASSWORD', '')
    
    print(f"\n Test Configuration:")
    print(f"   Proxy: {proxy_host}:{proxy_port}")
    print(f"   Username: {username}")
    print(f"   Password: {'*' * len(password) if password else 'None'}")
    print(f"\n{'='*80}")
    
    tests_passed = 0
    total_tests = 4
    
    # Test 1: Telegram API access
    if test_telegram_api(proxy_host, proxy_port, username, password):
        tests_passed += 1
    
    # Test 2: General web access
    if test_web_access(proxy_host, proxy_port, username, password):
        tests_passed += 1
    
    # Test 3: Data throughput
    if test_data_throughput(proxy_host, proxy_port, username, password):
        tests_passed += 1
    
    # Test 4: Multiple connections
    print("\n Testing multiple concurrent connections...")
    try:
        sock1 = socks5_connect(proxy_host, proxy_port, "httpbin.org", 80, username, password)
        sock2 = socks5_connect(proxy_host, proxy_port, "ifconfig.me", 80, username, password)
        
        success1 = test_http_request(sock1, "httpbin.org", "/uuid")
        success2 = test_http_request(sock2, "ifconfig.me", "/")
        
        sock1.close()
        sock2.close()
        
        if success1 and success2:
            print(" Multiple connections test successful")
            tests_passed += 1
        else:
            print(" Multiple connections test failed")
            
    except Exception as e:
        print(f" Multiple connections test failed: {e}")
    
    # Final results
    print(f"\n{'='*80}")
    print(f" TEST RESULTS: {tests_passed}/{total_tests} tests passed")
    
    if tests_passed == total_tests:
        print("\n ALL TESTS PASSED - PROXY IS WORKING CORRECTLY!")
        print(" Your SOCKS5 proxy is successfully routing data")
        print(" It's ready for Telegram and other applications")
    elif tests_passed > 0:
        print(f"\n PARTIAL SUCCESS - {tests_passed} tests passed")
        print(" Some functionality may be limited")
    else:
        print("\n ALL TESTS FAILED - PROXY IS NOT WORKING")
        print(" Check proxy configuration and logs")
        sys.exit(1)

if __name__ == '__main__':
    main() 