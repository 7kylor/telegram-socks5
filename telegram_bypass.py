#!/usr/bin/env python3
"""
Telegram Bypass Client - Use when main proxy is blocked
Download this file and run: python3 telegram_bypass.py
"""

import asyncio
import socket
import struct
import random
import time

# Server configuration - Auto-detected
SERVER_IP = None
USERNAME = "admin"
PASSWORD = None

# Bypass ports
MAIN_PORT = 1081
HTTP_TUNNEL_PORT = 8443
WEBSOCKET_PORT = 8444
PORT_HOP_RANGE = (8000, 9000)

async def test_socks5_connection(host, port):
    """Test SOCKS5 connection to a specific port"""
    try:
        reader, writer = await asyncio.open_connection(host, port)
        
        # SOCKS5 handshake
        handshake = struct.pack('!BBB', 5, 1, 2)
        writer.write(handshake)
        await writer.drain()
        
        response = await reader.read(2)
        if len(response) != 2:
            raise Exception("Invalid handshake")
        
        version, method = struct.unpack('!BB', response)
        if version != 5 or method != 2:
            raise Exception("Handshake failed")
        
        # Authentication
        auth_request = struct.pack('!BB', 1, len(USERNAME)) + USERNAME.encode()
        auth_request += struct.pack('!B', len(PASSWORD)) + PASSWORD.encode()
        
        writer.write(auth_request)
        await writer.drain()
        
        auth_response = await reader.read(2)
        if len(auth_response) != 2:
            raise Exception("Auth failed")
        
        auth_version, auth_status = struct.unpack('!BB', auth_response)
        if auth_status != 0:
            raise Exception("Auth rejected")
        
        # Test connection to Telegram
        request = struct.pack('!BBB', 5, 1, 0)  # Connect command
        request += struct.pack('!B', 3)  # Domain type
        target = 'api.telegram.org'
        request += struct.pack('!B', len(target)) + target.encode()
        request += struct.pack('!H', 443)
        
        writer.write(request)
        await writer.drain()
        
        connect_response = await reader.read(10)
        if len(connect_response) < 10:
            raise Exception("Connect failed")
        
        response_version, response_code = struct.unpack('!BB', connect_response[:2])
        if response_version != 5 or response_code != 0:
            raise Exception(f"Connect error: {response_code}")
        
        writer.close()
        await writer.wait_closed()
        return True
        
    except Exception as e:
        return False

async def find_working_port():
    """Find a working bypass port"""
    print(" Searching for working bypass ports...")
    
    # Test main port first
    print(f"   Testing main port {MAIN_PORT}...")
    if await test_socks5_connection(SERVER_IP, MAIN_PORT):
        return MAIN_PORT, "Main SOCKS5"
    
    # Test HTTP tunnel port
    print(f"   Testing HTTP tunnel port {HTTP_TUNNEL_PORT}...")
    if await test_socks5_connection(SERVER_IP, HTTP_TUNNEL_PORT):
        return HTTP_TUNNEL_PORT, "HTTP Tunnel"
    
    # Test WebSocket port
    print(f"   Testing WebSocket port {WEBSOCKET_PORT}...")
    if await test_socks5_connection(SERVER_IP, WEBSOCKET_PORT):
        return WEBSOCKET_PORT, "WebSocket Tunnel"
    
    # Test random ports in hopping range
    print(f"   Testing port hopping range {PORT_HOP_RANGE[0]}-{PORT_HOP_RANGE[1]}...")
    for _ in range(20):  # Try 20 random ports
        port = random.randint(*PORT_HOP_RANGE)
        if await test_socks5_connection(SERVER_IP, port):
            return port, "Port Hopping"
    
    return None, None

def load_config():
    """Load server configuration from environment or config files"""
    global SERVER_IP, PASSWORD
    
    # Try to get from environment variables
    import os
    SERVER_IP = os.getenv('PROXY_SERVER_IP')
    PASSWORD = os.getenv('PROXY_PASSWORD')
    
    # Try to detect from config files
    if not SERVER_IP or not PASSWORD:
        config_files = ['config/proxy.env', 'proxy.env', '.env']
        for config_file in config_files:
            try:
                if os.path.exists(config_file):
                    with open(config_file, 'r') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#') and '=' in line:
                                key, value = line.split('=', 1)
                                if key.strip() == 'ADMIN_PASSWORD' and not PASSWORD:
                                    PASSWORD = value.strip()
                    break
            except Exception:
                continue
    
    # Try to auto-detect server IP from connection info
    if not SERVER_IP:
        info_files = ['connection-info.txt', 'bypass-info.txt']
        for info_file in info_files:
            try:
                if os.path.exists(info_file):
                    with open(info_file, 'r') as f:
                        content = f.read()
                        # Look for IP patterns
                        import re
                        ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
                        ips = re.findall(ip_pattern, content)
                        for ip in ips:
                            if not ip.startswith('127.') and not ip.startswith('192.168.') and not ip.startswith('10.'):
                                SERVER_IP = ip
                                break
                        if SERVER_IP:
                            break
            except Exception:
                continue
    
    # Fallback: prompt user
    if not SERVER_IP:
        print(" Server IP not found. Please enter your proxy server IP:")
        SERVER_IP = input("Server IP: ").strip()
    
    if not PASSWORD:
        print(" Password not found. Please enter your proxy password:")
        import getpass
        PASSWORD = getpass.getpass("Password: ").strip()

async def main():
    print("=" * 60)
    print(" TELEGRAM BYPASS CLIENT")
    print("=" * 60)
    print()
    print(" Purpose: Connect to Telegram when main proxy is blocked")
    
    # Load configuration
    load_config()
    
    if not SERVER_IP or not PASSWORD:
        print("  Configuration incomplete. Cannot proceed.")
        return
    
    print(f" Server: {SERVER_IP}")
    print(f" Username: {USERNAME}")
    print(" Password: ********************************")
    print()
    
    # Find working port
    working_port, method = await find_working_port()
    
    if working_port:
        print(f" SUCCESS: Found working connection!")
        print(f"   Method: {method}")
        print(f"   Port: {working_port}")
        print()
        print(" TELEGRAM CONFIGURATION:")
        print("┌─────────────────────────────────────────────┐")
        print(f"│   Server: {SERVER_IP}")
        print(f"│   Port: {working_port}")
        print(f"│   Username: {USERNAME}")
        print(f"│   Password: {PASSWORD}")
        print("│   Type: SOCKS5")
        print("└─────────────────────────────────────────────┘")
        print()
        print(" TELEGRAM DIRECT LINK:")
        telegram_link = f"https://t.me/socks?server={SERVER_IP}&port={working_port}&user={USERNAME}&pass={PASSWORD}"
        print(f"   {telegram_link}")
        print()
        print(" Copy the settings above into Telegram!")
        
    else:
        print(" No working bypass ports found")
        print()
        print(" TROUBLESHOOTING:")
        print("   1. Check your internet connection")
        print("   2. Make sure bypass server is running on the server")
        print("   3. Try again in a few minutes (ports change every 5 minutes)")
        print("   4. Contact server administrator")

if __name__ == '__main__':
    asyncio.run(main()) 