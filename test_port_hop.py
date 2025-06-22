#!/usr/bin/env python3
import asyncio
import struct
import aiohttp
import json

async def get_current_port():
    """Get current active port from bypass server"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8443/port-info") as response:
                if response.status == 200:
                    port_info = await response.json()
                    return port_info.get('current_port')
    except Exception as e:
        print(f"Failed to get port info: {e}")
    return None

async def test_port_hop():
    try:
        # Get current active port
        current_port = await get_current_port()
        if not current_port:
            print("✗ Could not get current port from bypass server")
            return
            
        print(f"Testing port hopping connection to port {current_port}...")
        reader, writer = await asyncio.open_connection('localhost', current_port)
        print("✓ Connected to port hopping server")
        
        # SOCKS5 handshake
        handshake = struct.pack('!BBB', 5, 1, 2)
        writer.write(handshake)
        await writer.drain()
        
        response = await reader.read(2)
        print(f"Handshake response: {response}")
        
        if len(response) == 2:
            version, method = struct.unpack('!BB', response)
            print(f"SOCKS5 version: {version}, method: {method}")
            
            if version == 5 and method == 2:
                print("✓ SOCKS5 handshake successful")
                
                # Try authentication
                username = 'admin'
                password = 'PD1pF60k5H21ERb4z96uoflJtN612QyD'
                
                auth_request = struct.pack('!BB', 1, len(username)) + username.encode()
                auth_request += struct.pack('!B', len(password)) + password.encode()
                
                writer.write(auth_request)
                await writer.drain()
                
                auth_response = await reader.read(2)
                print(f"Auth response: {auth_response}")
                
                if len(auth_response) == 2:
                    version, status = struct.unpack('!BB', auth_response)
                    if status == 0:
                        print("✓ Authentication successful!")
                        print("✓ Port hopping bypass method is working!")
                    else:
                        print(f"✗ Authentication failed: {status}")
                else:
                    print("✗ Invalid auth response")
            else:
                print("✗ Invalid SOCKS5 handshake")
        else:
            print("✗ No handshake response")
        
        writer.close()
        await writer.wait_closed()
        
    except Exception as e:
        print(f"✗ Test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_port_hop()) 