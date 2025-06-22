#!/usr/bin/env python3
"""
Advanced Bypass Server for Telegram SOCKS5 Proxy
Implements multiple bypass techniques to avoid blocking
"""

import asyncio
import socket
import struct
import ssl
import base64
import random
import time
import hashlib
import json
import os
from typing import Dict, List, Optional, Tuple
import logging
from dataclasses import dataclass
from aiohttp import web, ClientSession
import aiohttp
from cryptography.fernet import Fernet

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class BypassConfig:
    """Configuration for bypass methods"""
    socks_host: str = 'localhost'
    socks_port: int = 1080
    socks_username: str = 'admin'
    socks_password: str = ''
    
    # Port hopping
    port_range: Tuple[int, int] = (8000, 9000)
    hop_interval: int = 300  # seconds
    
    # HTTP tunnel
    http_port: int = 8443
    websocket_port: int = 8444
    
    # Obfuscation
    obfuscation_key: bytes = None
    
    # Domain fronting
    fronting_domains: List[str] = None

class TrafficObfuscator:
    """Obfuscates traffic to avoid DPI detection"""
    
    def __init__(self, key: bytes = None):
        self.key = key or Fernet.generate_key()
        self.cipher = Fernet(self.key)
    
    def obfuscate(self, data: bytes) -> bytes:
        """Obfuscate outgoing data"""
        # Add random padding
        padding_size = random.randint(1, 16)
        padding = os.urandom(padding_size)
        
        # Encrypt the data
        encrypted = self.cipher.encrypt(data)
        
        # Add fake HTTP headers to look like web traffic
        fake_headers = self._generate_fake_http_headers()
        
        # Combine everything
        obfuscated = fake_headers.encode() + b'\r\n\r\n' + encrypted + padding
        return obfuscated
    
    def deobfuscate(self, data: bytes) -> bytes:
        """Deobfuscate incoming data"""
        try:
            # Split headers and body
            if b'\r\n\r\n' in data:
                _, body = data.split(b'\r\n\r\n', 1)
            else:
                body = data
            
            # Remove padding (try different lengths)
            for padding_size in range(1, 17):
                try:
                    encrypted_data = body[:-padding_size] if padding_size > 0 else body
                    decrypted = self.cipher.decrypt(encrypted_data)
                    return decrypted
                except:
                    continue
            
            # If deobfuscation fails, return original data
            return data
        except Exception as e:
            logger.warning(f"Deobfuscation failed: {e}")
            return data
    
    def _generate_fake_http_headers(self) -> str:
        """Generate fake HTTP headers to mimic web traffic"""
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
        ]
        
        fake_paths = ['/api/v1/data', '/static/js/app.js', '/images/logo.png', '/css/style.css']
        
        headers = f"GET {random.choice(fake_paths)} HTTP/1.1\r\n"
        headers += f"Host: cdn.cloudflare.com\r\n"
        headers += f"User-Agent: {random.choice(user_agents)}\r\n"
        headers += f"Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8\r\n"
        headers += f"Accept-Language: en-US,en;q=0.5\r\n"
        headers += f"Accept-Encoding: gzip, deflate\r\n"
        headers += f"Connection: keep-alive\r\n"
        
        return headers

class PortHopper:
    """Implements port hopping to avoid port-based blocking"""
    
    def __init__(self, config: BypassConfig):
        self.config = config
        self.current_port = None
        self.servers: Dict[int, asyncio.Server] = {}
        self.last_hop = 0
    
    async def start_hopping(self):
        """Start port hopping service"""
        logger.info("Starting port hopping service...")
        
        while True:
            current_time = time.time()
            
            # Check if it's time to hop
            if current_time - self.last_hop >= self.config.hop_interval:
                await self.hop_to_new_port()
                self.last_hop = current_time
            
            await asyncio.sleep(30)  # Check every 30 seconds
    
    async def hop_to_new_port(self):
        """Hop to a new random port"""
        new_port = random.randint(*self.config.port_range)
        
        # Make sure it's different from current port
        while new_port == self.current_port:
            new_port = random.randint(*self.config.port_range)
        
        try:
            # Start server on new port
            server = await asyncio.start_server(
                self.handle_hopped_connection,
                '0.0.0.0',
                new_port
            )
            
            self.servers[new_port] = server
            old_port = self.current_port
            self.current_port = new_port
            
            logger.info(f"Hopped from port {old_port} to {new_port}")
            
            # Close old server after delay
            if old_port and old_port in self.servers:
                await asyncio.sleep(60)  # Grace period
                self.servers[old_port].close()
                await self.servers[old_port].wait_closed()
                del self.servers[old_port]
                logger.info(f"Closed old port {old_port}")
        
        except Exception as e:
            logger.error(f"Failed to hop to port {new_port}: {e}")
    
    async def handle_hopped_connection(self, reader, writer):
        """Handle connections on hopped ports"""
        client_addr = writer.get_extra_info('peername')
        logger.info(f"Port hop connection from {client_addr}")
        
        # Forward to main SOCKS5 proxy
        try:
            # Connect to main proxy
            proxy_reader, proxy_writer = await asyncio.open_connection(
                self.config.socks_host, 
                self.config.socks_port
            )
            
            # Start bidirectional forwarding
            await asyncio.gather(
                self._forward_data(reader, proxy_writer, "client->proxy"),
                self._forward_data(proxy_reader, writer, "proxy->client"),
                return_exceptions=True
            )
        
        except Exception as e:
            logger.error(f"Port hop forwarding error: {e}")
        finally:
            writer.close()
            await writer.wait_closed()
    
    async def _forward_data(self, reader, writer, direction):
        """Forward data between connections"""
        try:
            while True:
                data = await reader.read(8192)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except Exception as e:
            logger.debug(f"Forward error ({direction}): {e}")
        finally:
            writer.close()

class HTTPTunnel:
    """HTTP tunnel to bypass HTTP-only firewalls"""
    
    def __init__(self, config: BypassConfig):
        self.config = config
        self.obfuscator = TrafficObfuscator(config.obfuscation_key)
    
    async def start_http_tunnel(self, port_hopper=None):
        """Start HTTP tunnel server"""
        app = web.Application()
        app['port_hopper'] = port_hopper  # Store reference to port hopper
        app.router.add_post('/tunnel', self.handle_http_tunnel)
        app.router.add_get('/health', self.health_check)
        app.router.add_get('/', self.serve_fake_website)
        
        # Add fake endpoints to look legitimate
        app.router.add_get('/api/status', self.fake_api)
        app.router.add_get('/static/{filename}', self.fake_static)
        app.router.add_get('/port-info', self.get_port_info)
        
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, '0.0.0.0', self.config.http_port)
        await site.start()
        
        logger.info(f"HTTP tunnel started on port {self.config.http_port}")
    
    async def handle_http_tunnel(self, request):
        """Handle HTTP tunnel requests"""
        try:
            # Read the tunneled data
            data = await request.read()
            
            # Deobfuscate if needed
            if self.config.obfuscation_key:
                data = self.obfuscator.deobfuscate(data)
            
            # Forward to SOCKS5 proxy
            reader, writer = await asyncio.open_connection(
                self.config.socks_host,
                self.config.socks_port
            )
            
            writer.write(data)
            await writer.drain()
            
            # Read response
            response_data = await reader.read(8192)
            
            writer.close()
            await writer.wait_closed()
            
            # Obfuscate response if needed
            if self.config.obfuscation_key:
                response_data = self.obfuscator.obfuscate(response_data)
            
            return web.Response(
                body=response_data,
                content_type='application/octet-stream',
                headers={
                    'Cache-Control': 'no-cache',
                    'Server': 'nginx/1.18.0'
                }
            )
        
        except Exception as e:
            logger.error(f"HTTP tunnel error: {e}")
            return web.Response(status=500, text="Internal Server Error")
    
    async def health_check(self, request):
        """Health check endpoint"""
        return web.json_response({'status': 'ok', 'service': 'cdn'})
    
    async def serve_fake_website(self, request):
        """Serve fake website to look legitimate"""
        fake_html = """
        <!DOCTYPE html>
        <html>
        <head><title>CDN Service</title></head>
        <body>
        <h1>Content Delivery Network</h1>
        <p>This is a CDN service for static content delivery.</p>
        <p>Status: Online</p>
        </body>
        </html>
        """
        return web.Response(text=fake_html, content_type='text/html')
    
    async def fake_api(self, request):
        """Fake API endpoint"""
        return web.json_response({
            'version': '1.2.3',
            'status': 'operational',
            'uptime': time.time(),
            'endpoints': ['/api/status', '/health', '/static/*']
        })
    
    async def fake_static(self, request):
        """Fake static file serving"""
        filename = request.match_info['filename']
        return web.Response(
            text=f"/* Static file: {filename} */\nbody {{ font-family: Arial; }}",
            content_type='text/css' if filename.endswith('.css') else 'text/plain'
        )
    
    async def get_port_info(self, request):
        """Get current port hopping info"""
        port_hopper = request.app.get('port_hopper')
        if port_hopper and port_hopper.current_port:
            info = {
                'current_port': port_hopper.current_port,
                'active_ports': list(port_hopper.servers.keys()),
                'port_range': port_hopper.config.port_range,
                'hop_interval': port_hopper.config.hop_interval
            }
            return web.json_response(info)
        else:
            return web.json_response({'current_port': None, 'active_ports': []}, status=404)

class WebSocketTunnel:
    """WebSocket tunnel for real-time communication"""
    
    def __init__(self, config: BypassConfig):
        self.config = config
        self.connections = {}
    
    async def start_websocket_tunnel(self):
        """Start WebSocket tunnel server"""
        app = web.Application()
        app.router.add_get('/ws', self.websocket_handler)
        app.router.add_get('/', self.serve_chat_app)
        
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, '0.0.0.0', self.config.websocket_port)
        await site.start()
        
        logger.info(f"WebSocket tunnel started on port {self.config.websocket_port}")
    
    async def websocket_handler(self, request):
        """Handle WebSocket connections"""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        connection_id = f"{time.time()}_{random.randint(1000, 9999)}"
        self.connections[connection_id] = ws
        
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.BINARY:
                    # Forward binary data to SOCKS5 proxy
                    await self.forward_to_proxy(msg.data, ws)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f'WebSocket error: {ws.exception()}')
                    break
        
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            if connection_id in self.connections:
                del self.connections[connection_id]
        
        return ws
    
    async def forward_to_proxy(self, data: bytes, ws):
        """Forward WebSocket data to SOCKS5 proxy"""
        try:
            reader, writer = await asyncio.open_connection(
                self.config.socks_host,
                self.config.socks_port
            )
            
            writer.write(data)
            await writer.drain()
            
            response = await reader.read(8192)
            
            writer.close()
            await writer.wait_closed()
            
            # Send response back via WebSocket
            await ws.send_bytes(response)
        
        except Exception as e:
            logger.error(f"WebSocket proxy forwarding error: {e}")
    
    async def serve_chat_app(self, request):
        """Serve fake chat application"""
        chat_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Chat Application</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                #messages { border: 1px solid #ccc; height: 300px; overflow-y: scroll; padding: 10px; }
                #messageInput { width: 80%; padding: 5px; }
                #sendButton { padding: 5px 10px; }
            </style>
        </head>
        <body>
            <h1>Secure Chat</h1>
            <div id="messages"></div>
            <input type="text" id="messageInput" placeholder="Type a message...">
            <button id="sendButton">Send</button>
            
            <script>
                // Fake chat application (non-functional, just for appearance)
                const messages = document.getElementById('messages');
                const input = document.getElementById('messageInput');
                const button = document.getElementById('sendButton');
                
                button.onclick = () => {
                    if (input.value.trim()) {
                        const div = document.createElement('div');
                        div.textContent = `You: ${input.value}`;
                        messages.appendChild(div);
                        input.value = '';
                        messages.scrollTop = messages.scrollHeight;
                    }
                };
                
                input.onkeypress = (e) => {
                    if (e.key === 'Enter') button.click();
                };
            </script>
        </body>
        </html>
        """
        return web.Response(text=chat_html, content_type='text/html')

class DomainFronting:
    """Domain fronting to bypass SNI-based blocking"""
    
    def __init__(self, config: BypassConfig):
        self.config = config
        self.fronting_domains = config.fronting_domains or [
            'cloudflare.com',
            'amazonaws.com', 
            'googleapis.com',
            'microsoft.com',
            'fastly.com'
        ]
    
    async def create_fronted_connection(self, target_host: str, target_port: int):
        """Create connection using domain fronting"""
        front_domain = random.choice(self.fronting_domains)
        
        # Create SSL context that will connect to front domain
        # but send SNI for target domain
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        try:
            # Connect to CDN/front domain
            reader, writer = await asyncio.open_connection(
                front_domain, 443, ssl=context
            )
            
            # Send HTTP CONNECT request for target
            connect_request = f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
            connect_request += f"Host: {target_host}:{target_port}\r\n"
            connect_request += "Proxy-Connection: keep-alive\r\n\r\n"
            
            writer.write(connect_request.encode())
            await writer.drain()
            
            # Read CONNECT response
            response = await reader.readline()
            if b'200' in response:
                logger.info(f"Domain fronting successful via {front_domain}")
                return reader, writer
            else:
                writer.close()
                raise Exception(f"CONNECT failed: {response}")
        
        except Exception as e:
            logger.error(f"Domain fronting failed via {front_domain}: {e}")
            raise

class BypassServer:
    """Main bypass server coordinating all bypass methods"""
    
    def __init__(self, config: BypassConfig):
        self.config = config
        self.port_hopper = PortHopper(config)
        self.http_tunnel = HTTPTunnel(config)
        self.websocket_tunnel = WebSocketTunnel(config)
        self.domain_fronting = DomainFronting(config)
    
    async def start_all_bypasses(self):
        """Start all bypass methods"""
        logger.info("Starting all bypass methods...")
        
        tasks = [
            asyncio.create_task(self.port_hopper.start_hopping()),
            asyncio.create_task(self.http_tunnel.start_http_tunnel(self.port_hopper)),
            asyncio.create_task(self.websocket_tunnel.start_websocket_tunnel()),
        ]
        
        # Start initial port hop
        await self.port_hopper.hop_to_new_port()
        
        logger.info("All bypass methods started successfully!")
        logger.info(f"Port hopping range: {self.config.port_range}")
        logger.info(f"HTTP tunnel: http://YOUR_SERVER:{self.config.http_port}")
        logger.info(f"WebSocket tunnel: ws://YOUR_SERVER:{self.config.websocket_port}/ws")
        
        # Wait for all tasks
        await asyncio.gather(*tasks, return_exceptions=True)

def load_bypass_config():
    """Load bypass configuration"""
    config = BypassConfig()
    
    # Load from environment or config file
    if os.path.exists('config/proxy.env'):
        with open('config/proxy.env', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    if key == 'ADMIN_PASSWORD':
                        config.socks_password = value
    
    # Override with environment variables
    config.socks_host = os.getenv('SOCKS_HOST', config.socks_host)
    config.socks_port = int(os.getenv('SOCKS_PORT', config.socks_port))
    config.socks_username = os.getenv('SOCKS_USERNAME', config.socks_username)
    config.socks_password = os.getenv('SOCKS_PASSWORD', config.socks_password)
    
    config.http_port = int(os.getenv('BYPASS_HTTP_PORT', config.http_port))
    config.websocket_port = int(os.getenv('BYPASS_WS_PORT', config.websocket_port))
    
    # Generate obfuscation key if not provided
    if not config.obfuscation_key:
        config.obfuscation_key = Fernet.generate_key()
    
    return config

async def main():
    """Main entry point"""
    config = load_bypass_config()
    bypass_server = BypassServer(config)
    
    try:
        await bypass_server.start_all_bypasses()
    except KeyboardInterrupt:
        logger.info("Bypass server stopped by user")
    except Exception as e:
        logger.error(f"Bypass server error: {e}")

if __name__ == '__main__':
    asyncio.run(main()) 