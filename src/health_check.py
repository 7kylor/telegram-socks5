#!/usr/bin/env python3
"""
Health check script for SOCKS5 proxy
"""

import socket
import sys
import struct
import os
import time

def check_socks5_health(host='localhost', port=1080, timeout=3, retries=2):
    """Check if SOCKS5 proxy is responding correctly"""
    for attempt in range(retries + 1):
        sock = None
        try:
            # Create socket connection
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            
            # Connect to proxy
            sock.connect((host, port))
            
            # Send SOCKS5 handshake (no auth method)
            handshake = struct.pack('!BBB', 5, 1, 0)
            sock.send(handshake)
            
            # Receive response
            response = sock.recv(2)
            if len(response) != 2:
                sock.close()
                if attempt < retries:
                    time.sleep(0.5)
                    continue
                return False
            
            version, method = struct.unpack('!BB', response)
            
            # Check if proxy accepted our handshake
            if version == 5 and method in (0, 2):  # No auth or username/password
                sock.close()
                return True
            
            sock.close()
            if attempt < retries:
                time.sleep(0.5)
                continue
            return False
            
        except Exception as e:
            if sock:
                sock.close()
            if attempt < retries:
                time.sleep(0.5)
                continue
            # Don't print errors for health checks to avoid log spam
            return False
    
    return False

def check_metrics_health(port=8080, timeout=5):
    """Check if metrics endpoint is accessible"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(('localhost', port))
        sock.close()
        return True
    except Exception:
        return False

def main():
    """Main health check function"""
    proxy_port = int(os.getenv('PROXY_PORT', '1080'))
    metrics_port = int(os.getenv('METRICS_PORT', '8080'))
    
    # Check SOCKS5 proxy
    if not check_socks5_health(port=proxy_port):
        print("SOCKS5 proxy health check failed")
        sys.exit(1)
    
    # Check metrics endpoint
    if not check_metrics_health(port=metrics_port):
        print("Metrics endpoint health check failed")
        sys.exit(1)
    
    print("All health checks passed")
    sys.exit(0)

if __name__ == '__main__':
    main() 