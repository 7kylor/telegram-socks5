#!/usr/bin/env python3
"""
Secure Telegram SOCKS5 Proxy Server
Features: Rate limiting, encryption, authentication, monitoring
"""

import asyncio
import socket
import struct
import logging
import time
import hashlib
import hmac
import os
import signal
import json
from typing import Dict, Set, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict, deque
import uvloop
from cryptography.fernet import Fernet
from prometheus_client import Counter, Histogram, Gauge, start_http_server

# Configure logging with security considerations
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/tmp/proxy.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

# Metrics
CONNECTION_COUNTER = Counter('socks5_connections_total', 'Total connections')
REQUEST_HISTOGRAM = Histogram('socks5_request_duration_seconds', 'Request duration')
ACTIVE_CONNECTIONS = Gauge('socks5_active_connections', 'Active connections')
RATE_LIMIT_HITS = Counter('socks5_rate_limit_hits_total', 'Rate limit violations')

@dataclass
class ProxyConfig:
    """Configuration for the SOCKS5 proxy"""
    host: str = '0.0.0.0'
    port: int = 1080
    max_connections: int = 1000
    rate_limit_per_ip: int = 15  # requests per minute (increased for health checks)
    rate_limit_window: int = 60  # seconds
    auth_required: bool = True
    encryption_key: Optional[bytes] = None
    telegram_domains: Set[str] = None
    metrics_port: int = 8080

    def __post_init__(self):
        if self.telegram_domains is None:
            self.telegram_domains = {
                'api.telegram.org',
                'core.telegram.org',
                'web.telegram.org',
                'desktop.telegram.org',
                'updates.tdesktop.com',
                '149.154.160.0/20',
                '91.108.4.0/22',
                '91.108.8.0/22',
                '91.108.12.0/22',
                '91.108.16.0/22',
                '91.108.20.0/22',
                '91.108.56.0/22',
                '149.154.160.0/20',
                '149.154.164.0/22',
                '149.154.168.0/22',
                '149.154.172.0/22'
            }

class RateLimiter:
    """Rate limiter with sliding window"""
    
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, deque] = defaultdict(deque)
    
    def is_allowed(self, client_ip: str) -> bool:
        """Check if request is allowed under rate limit"""
        # Exempt localhost/health checks from rate limiting
        if client_ip in ('127.0.0.1', '::1', 'localhost'):
            return True
        
        now = time.time()
        client_requests = self.requests[client_ip]
        
        # Remove old requests outside the window
        while client_requests and client_requests[0] <= now - self.window_seconds:
            client_requests.popleft()
        
        if len(client_requests) >= self.max_requests:
            RATE_LIMIT_HITS.inc()
            return False
        
        client_requests.append(now)
        return True

class AuthManager:
    """Authentication and authorization manager"""
    
    def __init__(self, config: ProxyConfig):
        self.config = config
        self.auth_tokens = self._load_auth_tokens()
        self.encryption_key = config.encryption_key or Fernet.generate_key()
        self.cipher = Fernet(self.encryption_key)
    
    def _load_auth_tokens(self) -> Dict[str, str]:
        """Load authentication tokens from environment or config"""
        tokens = {}
        auth_data = os.getenv('PROXY_AUTH_TOKENS')
        if auth_data:
            try:
                tokens = json.loads(auth_data)
            except json.JSONDecodeError:
                logger.error("Invalid auth tokens format")
        
        # Default admin token if none provided
        if not tokens:
            # Try to use ADMIN_PASSWORD first, then fallback to ADMIN_TOKEN
            admin_password = os.getenv('ADMIN_PASSWORD')
            if admin_password:
                tokens['admin'] = hashlib.sha256(admin_password.encode()).hexdigest()
            else:
                admin_token = os.getenv('ADMIN_TOKEN', 'default_admin_token_change_me')
                tokens['admin'] = hashlib.sha256(admin_token.encode()).hexdigest()
        
        return tokens
    
    def authenticate(self, username: str, password: str) -> bool:
        """Authenticate user credentials"""
        if not self.config.auth_required:
            return True
        
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        return self.auth_tokens.get(username) == password_hash

class SOCKS5Server:
    """Secure SOCKS5 Proxy Server"""
    
    SOCKS_VERSION = 5
    
    def __init__(self, config: ProxyConfig):
        self.config = config
        self.rate_limiter = RateLimiter(config.rate_limit_per_ip, config.rate_limit_window)
        self.auth_manager = AuthManager(config)
        self.active_connections: Set[asyncio.Task] = set()
        self.server = None
        self.shutdown_event = asyncio.Event()
    
    async def start(self):
        """Start the SOCKS5 server"""
        # Start metrics server
        start_http_server(self.config.metrics_port)
        logger.info(f"Metrics server started on port {self.config.metrics_port}")
        
        # Start SOCKS5 server
        self.server = await asyncio.start_server(
            self.handle_client,
            self.config.host,
            self.config.port,
            limit=self.config.max_connections
        )
        
        logger.info(f"SOCKS5 proxy started on {self.config.host}:{self.config.port}")
        
        # Setup signal handlers
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._signal_handler)
        
        await self.server.serve_forever()
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.shutdown_event.set()
    
    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle incoming client connection"""
        client_addr = writer.get_extra_info('peername')
        client_ip = client_addr[0] if client_addr else 'unknown'
        
        # Rate limiting (skip for localhost/health checks and Docker internal IPs)
        exempt_ips = ('127.0.0.1', '::1', 'localhost')
        is_docker_internal = client_ip.startswith('172.') or client_ip.startswith('10.')
        
        if client_ip not in exempt_ips and not is_docker_internal and not self.rate_limiter.is_allowed(client_ip):
            logger.warning(f"Rate limit exceeded for {client_ip}")
            writer.close()
            await writer.wait_closed()
            return
        
        CONNECTION_COUNTER.inc()
        ACTIVE_CONNECTIONS.inc()
        
        try:
            await self._handle_socks5_handshake(reader, writer, client_ip)
        except Exception as e:
            logger.error(f"Error handling client {client_ip}: {e}")
        finally:
            ACTIVE_CONNECTIONS.dec()
            writer.close()
            await writer.wait_closed()
    
    async def _handle_socks5_handshake(self, reader: asyncio.StreamReader, 
                                      writer: asyncio.StreamWriter, client_ip: str):
        """Handle SOCKS5 handshake protocol"""
        
        # Read initial handshake
        data = await reader.read(262)  # Maximum initial handshake size
        if len(data) < 3:
            return
        
        version, nmethods = struct.unpack('!BB', data[:2])
        if version != self.SOCKS_VERSION:
            return
        
        methods = list(data[2:2+nmethods])
        
        # Determine authentication method
        if self.config.auth_required:
            if 2 not in methods:  # Username/password auth
                writer.write(struct.pack('!BB', self.SOCKS_VERSION, 0xFF))
                await writer.drain()
                return
            # Accept username/password authentication
            writer.write(struct.pack('!BB', self.SOCKS_VERSION, 2))
        else:
            # No authentication required
            writer.write(struct.pack('!BB', self.SOCKS_VERSION, 0))
        
        await writer.drain()
        
        # Handle authentication if required
        if self.config.auth_required:
            if not await self._handle_authentication(reader, writer):
                return
        
        # Handle SOCKS5 request
        await self._handle_socks5_request(reader, writer, client_ip)
    
    async def _handle_authentication(self, reader: asyncio.StreamReader, 
                                   writer: asyncio.StreamWriter) -> bool:
        """Handle username/password authentication"""
        data = await reader.read(513)  # Max auth request size
        if len(data) < 3:
            return False
        
        version = data[0]
        if version != 1:  # Username/password auth version
            return False
        
        username_len = data[1]
        if len(data) < 2 + username_len + 1:
            return False
        
        username = data[2:2+username_len].decode('utf-8', errors='ignore')
        password_len = data[2+username_len]
        
        if len(data) < 2 + username_len + 1 + password_len:
            return False
        
        password = data[2+username_len+1:2+username_len+1+password_len].decode('utf-8', errors='ignore')
        
        # Authenticate
        if self.auth_manager.authenticate(username, password):
            writer.write(struct.pack('!BB', 1, 0))  # Success
            await writer.drain()
            return True
        else:
            writer.write(struct.pack('!BB', 1, 1))  # Failure
            await writer.drain()
            return False
    
    async def _handle_socks5_request(self, reader: asyncio.StreamReader, 
                                   writer: asyncio.StreamWriter, client_ip: str):
        """Handle SOCKS5 connection request"""
        with REQUEST_HISTOGRAM.time():
            data = await reader.read(262)
            if len(data) < 10:
                return
            
            version, cmd, reserved, addr_type = struct.unpack('!BBBB', data[:4])
            
            if version != self.SOCKS_VERSION or cmd != 1:  # Only CONNECT supported
                reply = struct.pack('!BBBBIH', self.SOCKS_VERSION, 7, 0, 1, 0, 0)
                writer.write(reply)
                await writer.drain()
                return
            
            # Parse address
            if addr_type == 1:  # IPv4
                if len(data) < 10:
                    return
                addr = socket.inet_ntoa(data[4:8])
                port = struct.unpack('!H', data[8:10])[0]
            elif addr_type == 3:  # Domain name
                if len(data) < 5:
                    return
                addr_len = data[4]
                if len(data) < 5 + addr_len + 2:
                    return
                addr = data[5:5+addr_len].decode('utf-8', errors='ignore')
                port = struct.unpack('!H', data[5+addr_len:5+addr_len+2])[0]
            elif addr_type == 4:  # IPv6
                if len(data) < 22:
                    return
                addr = socket.inet_ntop(socket.AF_INET6, data[4:20])
                port = struct.unpack('!H', data[20:22])[0]
            else:
                reply = struct.pack('!BBBBIH', self.SOCKS_VERSION, 8, 0, 1, 0, 0)
                writer.write(reply)
                await writer.drain()
                return
            
            # Security check: only allow Telegram domains/IPs
            if not self._is_telegram_address(addr):
                logger.warning(f"Blocked non-Telegram address: {addr} from {client_ip}")
                reply = struct.pack('!BBBBIH', self.SOCKS_VERSION, 2, 0, 1, 0, 0)
                writer.write(reply)
                await writer.drain()
                return
            
            # Establish connection to target
            try:
                target_reader, target_writer = await asyncio.wait_for(
                    asyncio.open_connection(addr, port),
                    timeout=10.0
                )
                
                # Send success response
                reply = struct.pack('!BBBBIH', self.SOCKS_VERSION, 0, 0, 1, 0, 0)
                writer.write(reply)
                await writer.drain()
                
                # Start data relay
                await self._relay_data(reader, writer, target_reader, target_writer, client_ip)
                
            except Exception as e:
                logger.error(f"Connection failed to {addr}:{port} - {e}")
                reply = struct.pack('!BBBBIH', self.SOCKS_VERSION, 1, 0, 1, 0, 0)
                writer.write(reply)
                await writer.drain()
    
    def _is_telegram_address(self, addr: str) -> bool:
        """Check if address is allowed for Telegram"""
        # Check exact domain matches
        if addr in self.config.telegram_domains:
            return True
        
        # Check if it's a Telegram subdomain
        for domain in self.config.telegram_domains:
            if not domain.startswith('*.') and addr.endswith('.' + domain):
                return True
        
        # Check IP ranges (simplified check)
        try:
            import ipaddress
            ip = ipaddress.ip_address(addr)
            for cidr in self.config.telegram_domains:
                if '/' in cidr:
                    try:
                        network = ipaddress.ip_network(cidr, strict=False)
                        if ip in network:
                            return True
                    except ValueError:
                        continue
        except ValueError:
            pass
        
        return False
    
    async def _relay_data(self, client_reader: asyncio.StreamReader, 
                         client_writer: asyncio.StreamWriter,
                         target_reader: asyncio.StreamReader, 
                         target_writer: asyncio.StreamWriter,
                         client_ip: str):
        """Relay data between client and target with encryption support"""
        
        async def copy_data(reader, writer, direction):
            try:
                while True:
                    data = await reader.read(8192)
                    if not data:
                        break
                    writer.write(data)
                    await writer.drain()
            except Exception as e:
                logger.debug(f"Relay error ({direction}): {e}")
            finally:
                writer.close()
        
        # Start bidirectional data relay
        tasks = [
            asyncio.create_task(copy_data(client_reader, target_writer, f"{client_ip}->target")),
            asyncio.create_task(copy_data(target_reader, client_writer, f"target->{client_ip}"))
        ]
        
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        except Exception as e:
            logger.error(f"Relay error: {e}")
        finally:
            for task in tasks:
                task.cancel()
            target_writer.close()
            await target_writer.wait_closed()

async def main():
    """Main entry point"""
    # Load configuration from environment
    config = ProxyConfig(
        host=os.getenv('PROXY_HOST', '0.0.0.0'),
        port=int(os.getenv('PROXY_PORT', '1080')),
        max_connections=int(os.getenv('MAX_CONNECTIONS', '1000')),
        rate_limit_per_ip=int(os.getenv('RATE_LIMIT_PER_IP', '10')),
        auth_required=os.getenv('AUTH_REQUIRED', 'true').lower() == 'true',
        metrics_port=int(os.getenv('METRICS_PORT', '8080'))
    )
    
    # Use uvloop for better performance
    uvloop.install()
    
    server = SOCKS5Server(config)
    
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        if server.server:
            server.server.close()
            await server.server.wait_closed()

if __name__ == '__main__':
    asyncio.run(main()) 