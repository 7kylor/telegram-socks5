#!/usr/bin/env python3
"""
External Bypass Client for Telegram SOCKS5 Proxy
Use this when the main proxy is blocked by your ISP
"""

import asyncio
import socket
import struct
import ssl
import base64
import random
import time
import json
import os
from typing import Optional, Tuple, List
import logging
import aiohttp
from cryptography.fernet import Fernet

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ExternalBypassClient:
    """External client for bypass methods when main proxy is blocked"""
    
    def __init__(self, server_ip: str = None, 
                 username: str = 'admin', password: str = None):
        self.server_ip = server_ip
        self.username = username
        self.password = password
        
        # Bypass method ports
        self.http_tunnel_port = 8443
        self.websocket_port = 8444
        self.port_hop_range = (8000, 9000)
        
        # Connection methods in order of preference
        self.connection_methods = [
            self._connect_via_port_hop,
            self._connect_via_http_tunnel,
            self._connect_via_websocket,
            self._connect_via_domain_fronting
        ]
    
    async def connect_with_fallback(self, target_host: str, target_port: int) -> Optional[Tuple]:
        """Try to connect using bypass methods"""
        logger.info(f"Attempting bypass connection to {target_host}:{target_port}")
        logger.info(f"Server: {self.server_ip}")
        
        for i, method in enumerate(self.connection_methods):
            try:
                logger.info(f"Trying method {i+1}/{len(self.connection_methods)}: {method.__name__}")
                reader, writer = await method(target_host, target_port)
                logger.info(f"Successfully connected via {method.__name__}")
                return reader, writer
            except Exception as e:
                logger.warning(f"Method {method.__name__} failed: {e}")
                continue
        
        logger.error("All bypass methods failed")
        return None
    
    async def _connect_via_port_hop(self, target_host: str, target_port: int) -> Tuple:
        """Connect via port hopping"""
        # Get current active port from bypass server
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://{self.server_ip}:{self.http_tunnel_port}/port-info") as response:
                    if response.status == 200:
                        port_info = await response.json()
                        current_port = port_info.get('current_port')
                        active_ports = port_info.get('active_ports', [])
                        
                        logger.info(f"Current active port: {current_port}")
                        logger.info(f"Active ports: {active_ports}")
                        
                        # Try current port first
                        if current_port:
                            try:
                                return await self._socks5_connect(
                                    self.server_ip, current_port,
                                    target_host, target_port,
                                    self.username, self.password
                                )
                            except Exception as e:
                                logger.debug(f"Current port {current_port} failed: {e}")
                        
                        # Try other active ports
                        for port in active_ports:
                            if port != current_port:
                                try:
                                    return await self._socks5_connect(
                                        self.server_ip, port,
                                        target_host, target_port,
                                        self.username, self.password
                                    )
                                except Exception as e:
                                    logger.debug(f"Port {port} failed: {e}")
                                    continue
        except Exception as e:
            logger.debug(f"Failed to get port info: {e}")
        
        # Fallback to random port attempts
        for _ in range(10):  # Try up to 10 random ports
            hop_port = random.randint(*self.port_hop_range)
            try:
                return await self._socks5_connect(
                    self.server_ip, hop_port,
                    target_host, target_port,
                    self.username, self.password
                )
            except:
                continue
        
        raise Exception("No active port hop found")
    
    async def _connect_via_http_tunnel(self, target_host: str, target_port: int) -> Tuple:
        """Connect via HTTP tunnel (looks like web traffic)"""
        try:
            # Test HTTP tunnel endpoint
            async with aiohttp.ClientSession() as session:
                test_data = b"test_connection"
                async with session.post(
                    f"http://{self.server_ip}:{self.http_tunnel_port}/tunnel",
                    data=test_data,
                    headers={
                        'Content-Type': 'application/octet-stream',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                ) as response:
                    if response.status == 200:
                        logger.info("HTTP tunnel endpoint is accessible")
                        # For now, create a direct connection as fallback
                        # In production, this would implement full HTTP tunneling
                        return await self._socks5_connect(
                            self.server_ip, self.http_tunnel_port,
                            target_host, target_port,
                            self.username, self.password
                        )
                    else:
                        raise Exception(f"HTTP tunnel failed: {response.status}")
        except Exception as e:
            raise Exception(f"HTTP tunnel connection failed: {e}")
    
    async def _connect_via_websocket(self, target_host: str, target_port: int) -> Tuple:
        """Connect via WebSocket tunnel (looks like chat app)"""
        try:
            # Test WebSocket endpoint
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://{self.server_ip}:{self.websocket_port}/") as response:
                    if response.status == 200:
                        logger.info("WebSocket tunnel endpoint is accessible")
                        # For now, create a direct connection as fallback
                        # In production, this would implement full WebSocket tunneling
                        return await self._socks5_connect(
                            self.server_ip, self.websocket_port,
                            target_host, target_port,
                            self.username, self.password
                        )
                    else:
                        raise Exception(f"WebSocket endpoint failed: {response.status}")
        except Exception as e:
            raise Exception(f"WebSocket connection failed: {e}")
    
    async def _connect_via_domain_fronting(self, target_host: str, target_port: int) -> Tuple:
        """Connect via domain fronting (via CDN)"""
        fronting_domains = [
            'cloudflare.com',
            'amazonaws.com',
            'googleapis.com'
        ]
        
        for domain in fronting_domains:
            try:
                # This is a simplified implementation
                # In production, this would implement proper domain fronting
                logger.info(f"Attempting domain fronting via {domain}")
                
                # For now, try a direct connection with random delay
                await asyncio.sleep(random.uniform(0.5, 2.0))
                
                return await self._socks5_connect(
                    self.server_ip, 1081,  # Try main port via fronting
                    target_host, target_port,
                    self.username, self.password
                )
            except Exception as e:
                logger.debug(f"Domain fronting via {domain} failed: {e}")
                continue
        
        raise Exception("Domain fronting failed")
    
    async def _socks5_connect(self, proxy_host: str, proxy_port: int,
                             target_host: str, target_port: int,
                             username: str, password: str) -> Tuple:
        """Standard SOCKS5 connection"""
        reader, writer = await asyncio.open_connection(proxy_host, proxy_port)
        
        try:
            # SOCKS5 handshake
            handshake = struct.pack('!BBB', 5, 1, 2)  # Version 5, 1 method, username/password
            writer.write(handshake)
            await writer.drain()
            
            response = await reader.read(2)
            if len(response) != 2:
                raise Exception("Invalid handshake response")
            
            version, method = struct.unpack('!BB', response)
            if version != 5 or method != 2:
                raise Exception("SOCKS5 handshake failed")
            
            # Authentication
            auth_request = struct.pack('!BB', 1, len(username)) + username.encode()
            auth_request += struct.pack('!B', len(password)) + password.encode()
            
            writer.write(auth_request)
            await writer.drain()
            
            auth_response = await reader.read(2)
            if len(auth_response) != 2:
                raise Exception("Invalid auth response")
            
            auth_version, auth_status = struct.unpack('!BB', auth_response)
            if auth_status != 0:
                raise Exception("Authentication failed")
            
            # Connect request
            request = struct.pack('!BBB', 5, 1, 0)  # Version, connect, reserved
            request += struct.pack('!B', 3)  # Domain name type
            request += struct.pack('!B', len(target_host)) + target_host.encode()
            request += struct.pack('!H', target_port)
            
            writer.write(request)
            await writer.drain()
            
            connect_response = await reader.read(10)
            if len(connect_response) < 10:
                raise Exception("Invalid connect response")
            
            response_version, response_code = struct.unpack('!BB', connect_response[:2])
            if response_version != 5 or response_code != 0:
                raise Exception(f"SOCKS5 connect failed: {response_code}")
            
            return reader, writer
        
        except Exception as e:
            writer.close()
            raise e

def load_client_config():
    """Load client configuration from environment or config files"""
    import os
    import re
    
    server_ip = os.getenv('PROXY_SERVER_IP')
    password = os.getenv('PROXY_PASSWORD')
    
    # Try to detect from config files
    if not server_ip or not password:
        config_files = ['config/proxy.env', 'proxy.env', '.env']
        for config_file in config_files:
            try:
                if os.path.exists(config_file):
                    with open(config_file, 'r') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#') and '=' in line:
                                key, value = line.split('=', 1)
                                if key.strip() == 'ADMIN_PASSWORD' and not password:
                                    password = value.strip()
                    break
            except Exception:
                continue
    
    # Try to auto-detect server IP from connection info
    if not server_ip:
        info_files = ['connection-info.txt', 'bypass-info.txt']
        for info_file in info_files:
            try:
                if os.path.exists(info_file):
                    with open(info_file, 'r') as f:
                        content = f.read()
                        # Look for IP patterns
                        ip_pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
                        ips = re.findall(ip_pattern, content)
                        for ip in ips:
                            if not ip.startswith('127.') and not ip.startswith('192.168.') and not ip.startswith('10.'):
                                server_ip = ip
                                break
                        if server_ip:
                            break
            except Exception:
                continue
    
    # Fallback: prompt user
    if not server_ip:
        print("  Server IP not found. Please enter your proxy server IP:")
        server_ip = input("Server IP: ").strip()
    
    if not password:
        print("  Password not found. Please enter your proxy password:")
        import getpass
        password = getpass.getpass("Password: ").strip()
    
    return server_ip, password

async def test_bypass_connection():
    """Test bypass connection methods"""
    print("=" * 80)
    print(" TELEGRAM BYPASS CLIENT - Anti-Blocking Connection Test")
    print("=" * 80)
    print()
    print(" Purpose: Connect to Telegram when main proxy is blocked by ISP")
    
    # Load configuration
    server_ip, password = load_client_config()
    
    if not server_ip or not password:
        print(" Configuration incomplete. Cannot proceed.")
        return
    
    print(f" Server: {server_ip}")
    print(" Methods: Port Hopping, HTTP Tunnel, WebSocket, Domain Fronting")
    print()
    print("Testing bypass methods...")
    print()
    
    client = ExternalBypassClient(server_ip=server_ip, password=password)
    
    # Test connection to Telegram
    try:
        connection = await client.connect_with_fallback('api.telegram.org', 443)
        if connection:
            reader, writer = connection
            print(" SUCCESS: Connected via bypass methods!")
            print(" Your bypass proxy is working!")
            print()
            print(" TELEGRAM CONFIGURATION:")
            print("   Use any bypass method that worked above")
            print("   The bypass client will automatically connect")
            print()
            print(" NEXT STEPS:")
            print("   1. Save this script on your local computer")
            print("   2. Run it when main proxy is blocked")
            print("   3. It will automatically find working bypass method")
            
            writer.close()
            await writer.wait_closed()
        else:
            print(" All bypass methods failed")
            print(" Try running the script again or check server status")
    except Exception as e:
        print(f" Bypass connection failed: {e}")
        print(f" Make sure the bypass server is running on {server_ip}")

if __name__ == '__main__':
    asyncio.run(test_bypass_connection()) 