#!/usr/bin/env python3
"""
Bypass Client for Telegram SOCKS5 Proxy
Automatically tries different bypass methods when main proxy is blocked
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

class BypassClient:
    """Client that can connect through various bypass methods"""
    
    def __init__(self, server_ip: str, main_port: int = 1081, 
                 username: str = 'admin', password: str = ''):
        self.server_ip = server_ip
        self.main_port = main_port
        self.username = username
        self.password = password
        
        # Bypass method ports
        self.http_tunnel_port = 8443
        self.websocket_port = 8444
        self.port_hop_range = (8000, 9000)
        
        # Connection methods in order of preference
        self.connection_methods = [
            self._connect_direct,
            self._connect_via_http_tunnel,
            self._connect_via_websocket,
            self._connect_via_port_hop,
            self._connect_via_domain_fronting
        ]
    
    async def connect_with_fallback(self, target_host: str, target_port: int) -> Optional[Tuple]:
        """Try to connect using various bypass methods"""
        logger.info(f"Attempting to connect to {target_host}:{target_port}")
        
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
    
    async def _connect_direct(self, target_host: str, target_port: int) -> Tuple:
        """Try direct connection to main SOCKS5 proxy"""
        return await self._socks5_connect(
            self.server_ip, self.main_port, 
            target_host, target_port,
            self.username, self.password
        )
    
    async def _connect_via_http_tunnel(self, target_host: str, target_port: int) -> Tuple:
        """Connect via HTTP tunnel"""
        # Create SOCKS5 request data
        socks_data = await self._build_socks5_request(target_host, target_port)
        
        # Send via HTTP tunnel (connect to bypass server)
        tunnel_host = "localhost" if self.server_ip in ['127.0.0.1', 'localhost'] else self.server_ip
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"http://{tunnel_host}:{self.http_tunnel_port}/tunnel",
                data=socks_data,
                headers={
                    'Content-Type': 'application/octet-stream',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            ) as response:
                if response.status == 200:
                    response_data = await response.read()
                    # Create mock reader/writer for HTTP tunnel
                    return await self._create_http_tunnel_connection(response_data)
                else:
                    raise Exception(f"HTTP tunnel failed: {response.status}")
    
    async def _connect_via_websocket(self, target_host: str, target_port: int) -> Tuple:
        """Connect via WebSocket tunnel"""
        ws_host = "localhost" if self.server_ip in ['127.0.0.1', 'localhost'] else self.server_ip
        session = aiohttp.ClientSession()
        ws = await session.ws_connect(f"ws://{ws_host}:{self.websocket_port}/ws")
        
        # Send SOCKS5 request via WebSocket
        socks_data = await self._build_socks5_request(target_host, target_port)
        await ws.send_bytes(socks_data)
        
        # Wait for response
        msg = await ws.receive()
        if msg.type == aiohttp.WSMsgType.BINARY:
            # Create mock reader/writer for WebSocket
            return await self._create_websocket_connection(ws, session)
        else:
            await session.close()
            raise Exception("WebSocket tunnel failed")
    
    async def _connect_via_port_hop(self, target_host: str, target_port: int) -> Tuple:
        """Connect via port hopping"""
        # Get current active port from bypass server
        try:
            # Use the correct server IP for port info endpoint
            port_info_host = "localhost" if self.server_ip in ['127.0.0.1', 'localhost'] else self.server_ip
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://{port_info_host}:{self.http_tunnel_port}/port-info") as response:
                    if response.status == 200:
                        port_info = await response.json()
                        current_port = port_info.get('current_port')
                        active_ports = port_info.get('active_ports', [])
                        
                        # Try current port first
                        if current_port:
                            try:
                                return await self._socks5_connect(
                                    port_info_host, current_port,
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
                                        port_info_host, port,
                                        target_host, target_port,
                                        self.username, self.password
                                    )
                                except Exception as e:
                                    logger.debug(f"Port {port} failed: {e}")
                                    continue
        except Exception as e:
            logger.debug(f"Failed to get port info: {e}")
        
        # Fallback to random port attempts
        fallback_host = "localhost" if self.server_ip in ['127.0.0.1', 'localhost'] else self.server_ip
        for _ in range(5):  # Try up to 5 random ports
            hop_port = random.randint(*self.port_hop_range)
            try:
                return await self._socks5_connect(
                    fallback_host, hop_port,
                    target_host, target_port,
                    self.username, self.password
                )
            except:
                continue
        
        raise Exception("No active port hop found")
    
    async def _connect_via_domain_fronting(self, target_host: str, target_port: int) -> Tuple:
        """Connect via domain fronting"""
        fronting_domains = [
            'cloudflare.com',
            'amazonaws.com',
            'googleapis.com',
            'microsoft.com'
        ]
        
        for domain in fronting_domains:
            try:
                # Create SSL connection to fronting domain
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                
                reader, writer = await asyncio.open_connection(
                    domain, 443, ssl=context
                )
                
                # Send CONNECT request
                connect_request = f"CONNECT {self.server_ip}:{self.main_port} HTTP/1.1\r\n"
                connect_request += f"Host: {self.server_ip}:{self.main_port}\r\n"
                connect_request += "Proxy-Connection: keep-alive\r\n\r\n"
                
                writer.write(connect_request.encode())
                await writer.drain()
                
                # Read CONNECT response
                response = await reader.readline()
                if b'200' in response:
                    # Now we can use this connection as SOCKS5
                    return await self._socks5_handshake_over_connection(
                        reader, writer, target_host, target_port
                    )
                else:
                    writer.close()
                    continue
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
    
    async def _build_socks5_request(self, target_host: str, target_port: int) -> bytes:
        """Build SOCKS5 request data for tunneling"""
        # Handshake
        handshake = struct.pack('!BBB', 5, 1, 2)
        
        # Authentication
        auth_request = struct.pack('!BB', 1, len(self.username)) + self.username.encode()
        auth_request += struct.pack('!B', len(self.password)) + self.password.encode()
        
        # Connect request
        connect_request = struct.pack('!BBB', 5, 1, 0)
        connect_request += struct.pack('!B', 3)
        connect_request += struct.pack('!B', len(target_host)) + target_host.encode()
        connect_request += struct.pack('!H', target_port)
        
        return handshake + auth_request + connect_request
    
    async def _create_http_tunnel_connection(self, response_data: bytes):
        """Create mock connection for HTTP tunnel"""
        # This is a simplified implementation
        # In practice, you'd need to handle the full HTTP tunnel protocol
        raise NotImplementedError("HTTP tunnel connection not fully implemented")
    
    async def _create_websocket_connection(self, ws, session):
        """Create mock connection for WebSocket tunnel"""
        # This is a simplified implementation
        # In practice, you'd need to handle the full WebSocket tunnel protocol
        raise NotImplementedError("WebSocket tunnel connection not fully implemented")
    
    async def _socks5_handshake_over_connection(self, reader, writer, target_host: str, target_port: int):
        """Perform SOCKS5 handshake over existing connection"""
        return await self._socks5_connect_with_connection(reader, writer, target_host, target_port)
    
    async def _socks5_connect_with_connection(self, reader, writer, target_host: str, target_port: int):
        """SOCKS5 connect using existing connection"""
        # Handshake
        handshake = struct.pack('!BBB', 5, 1, 2)
        writer.write(handshake)
        await writer.drain()
        
        response = await reader.read(2)
        version, method = struct.unpack('!BB', response)
        
        # Authentication
        auth_request = struct.pack('!BB', 1, len(self.username)) + self.username.encode()
        auth_request += struct.pack('!B', len(self.password)) + self.password.encode()
        
        writer.write(auth_request)
        await writer.drain()
        
        auth_response = await reader.read(2)
        auth_version, auth_status = struct.unpack('!BB', auth_response)
        
        if auth_status != 0:
            raise Exception("Authentication failed")
        
        # Connect request
        request = struct.pack('!BBB', 5, 1, 0)
        request += struct.pack('!B', 3)
        request += struct.pack('!B', len(target_host)) + target_host.encode()
        request += struct.pack('!H', target_port)
        
        writer.write(request)
        await writer.drain()
        
        connect_response = await reader.read(10)
        response_version, response_code = struct.unpack('!BB', connect_response[:2])
        
        if response_code != 0:
            raise Exception(f"Connect failed: {response_code}")
        
        return reader, writer

def load_client_config():
    """Load client configuration"""
    config = {}
    
    # Try to load from config file
    if os.path.exists('config/proxy.env'):
        with open('config/proxy.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    
    # Detect server IP - try multiple methods
    server_ip = '127.0.0.1'  # fallback
    
    # Method 1: Get from environment
    if os.getenv('SERVER_IP'):
        server_ip = os.getenv('SERVER_IP')
    
    # Method 2: Auto-detect real server IP
    else:
        try:
            import subprocess
            import socket
            
            # Try to get external IP
            try:
                result = subprocess.run(['curl', '-s', '--connect-timeout', '5', 'http://ifconfig.me'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0 and result.stdout.strip():
                    detected_ip = result.stdout.strip()
                    # Verify it's not localhost
                    if detected_ip not in ['127.0.0.1', 'localhost']:
                        server_ip = detected_ip
            except:
                pass
            
            # Method 3: Check if we can connect to localhost:1081 (local testing)
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex(('127.0.0.1', 1081))
                sock.close()
                if result == 0:  # Connection successful
                    server_ip = '127.0.0.1'  # Use localhost for local testing
            except:
                pass
                
        except Exception as e:
            logger.debug(f"Server IP detection failed: {e}")
    
    # Get the correct main port (1081 for external Docker mapping)
    main_port = 1081
    if server_ip in ['127.0.0.1', 'localhost']:
        main_port = int(config.get('PROXY_PORT', 1081))  # Use config port for local
    
    return {
        'server_ip': server_ip,
        'main_port': main_port,
        'username': 'admin',
        'password': config.get('ADMIN_PASSWORD', '')
    }

async def test_bypass_connection():
    """Test bypass connection methods"""
    config = load_client_config()
    
    client = BypassClient(
        server_ip=config['server_ip'],
        main_port=config['main_port'],
        username=config['username'],
        password=config['password']
    )
    
    print(f"Testing bypass connection to {config['server_ip']}:{config['main_port']}")
    print(f"Username: {config['username']}")
    print(f"Password: {'*' * len(config['password'])}")
    print()
    
    # Test connection to Telegram
    try:
        connection = await client.connect_with_fallback('api.telegram.org', 443)
        if connection:
            reader, writer = connection
            print(" Successfully connected via bypass methods!")
            print(" Your bypass proxy is working!")
            writer.close()
            await writer.wait_closed()
        else:
            print(" All bypass methods failed")
    except Exception as e:
        print(f" Bypass connection failed: {e}")

if __name__ == '__main__':
    asyncio.run(test_bypass_connection()) 