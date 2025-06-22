# Telegram SOCKS5 Proxy - Anti-Blocking Guide

## When Your Proxy Gets Blocked

If your SOCKS5 proxy gets blocked or censored, this guide provides multiple advanced bypass techniques to maintain connectivity.

## Available Bypass Methods

### 1. **Port Hopping**

- **What it is**: Automatically changes ports every 5 minutes
- **Port range**: 8000-9000
- **How it works**: Makes blocking difficult as the port constantly changes
- **Best for**: Port-based blocking

### 2. **HTTP Tunnel**

- **What it is**: Disguises SOCKS5 traffic as regular web traffic
- **Port**: 8443
- **How it works**: Wraps proxy traffic in HTTP requests
- **Best for**: Deep Packet Inspection (DPI) bypass

### 3. **WebSocket Tunnel**

- **What it is**: Makes proxy traffic look like a chat application
- **Port**: 8444
- **How it works**: Uses WebSocket protocol to tunnel data
- **Best for**: Application-layer filtering

### 4. **Domain Fronting**

- **What it is**: Routes traffic through legitimate CDN providers
- **How it works**: Uses CloudFlare, AWS, Google as intermediaries
- **Best for**: IP-based blocking

### 5. **Traffic Obfuscation**

- **What it is**: Encrypts and disguises traffic patterns
- **How it works**: Adds fake HTTP headers and random padding
- **Best for**: Traffic analysis resistance

## Quick Start

### Step 1: Deploy Main Proxy

```bash
./deploy.sh
```

### Step 2: Enable Bypass Methods

```bash
./start-bypass.sh
```

### Step 3: Test Connection

```bash
python3 src/bypass_client.py
```

## Telegram Configuration

### Normal Connection (if not blocked)

```
Server: YOUR_SERVER_IP
Port: 1081
Username: admin
Password: YOUR_AUTO_GENERATED_PASSWORD
Type: SOCKS5
```

### If Main Proxy is Blocked

The bypass client automatically tries alternative methods:

1. **Direct SOCKS5** (port 1081)
2. **HTTP Tunnel** (port 8443)
3. **WebSocket** (port 8444)
4. **Port Hopping** (ports 8000-9000)
5. **Domain Fronting** (via CDN)

## Manual Bypass Configuration

### HTTP Tunnel Method

If you need to manually configure HTTP tunneling:

```python
import aiohttp

async def connect_via_http():
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"http://YOUR_SERVER:8443/tunnel",
            data=socks5_request_data
        ) as response:
            return await response.read()
```

### WebSocket Method

For WebSocket tunneling:

```javascript
const ws = new WebSocket('ws://YOUR_SERVER:8444/ws');
ws.binaryType = 'arraybuffer';
ws.onopen = () => {
    ws.send(socks5RequestData);
};
```

## Advanced Usage

### Custom Port Hopping

Modify port range in `src/bypass_server.py`:

```python
port_range: Tuple[int, int] = (9000, 10000)  # Custom range
hop_interval: int = 180  # 3 minutes
```

### Custom Obfuscation

Add your own obfuscation key:

```bash
export OBFUSCATION_KEY="your-secret-key"
./start-bypass.sh
```

### Custom Domain Fronting

Edit fronting domains in `src/bypass_server.py`:

```python
fronting_domains = [
    'your-cdn-domain.com',
    'another-cdn.net'
]
```

## Monitoring & Management

### Check Bypass Status

```bash
# View running processes
ps aux | grep bypass_server

# Check logs
tail -f bypass-server.log

# Test connection
python3 src/bypass_client.py
```

### Stop Bypass Server

```bash
./stop-bypass.sh
```

### Restart Bypass Server

```bash
./stop-bypass.sh
./start-bypass.sh
```

## Troubleshooting

### Connection Issues

1. **Check main proxy is running**:

   ```bash
   docker ps | grep telegram-socks5
   ```

2. **Verify bypass server is running**:

   ```bash
   ps aux | grep bypass_server
   ```

3. **Check firewall ports**:

   ```bash
   netstat -tlnp | grep -E "(8443|8444|80[0-9][0-9])"
   ```

4. **Test individual methods**:

   ```bash
   # Test HTTP tunnel
   curl -X POST http://YOUR_SERVER:8443/health
   
   # Test WebSocket
   curl -H "Upgrade: websocket" http://YOUR_SERVER:8444/
   ```

### Common Problems

**Problem**: Bypass server won't start
**Solution**:

```bash
# Install dependencies
pip3 install aiohttp cryptography

# Check logs
cat bypass-server.log
```

**Problem**: All methods fail
**Solution**:

```bash
# Restart everything
./stop-bypass.sh
./stop-proxy.sh
./start-proxy.sh
./start-bypass.sh
```

**Problem**: Port hopping not working
**Solution**:

```bash
# Check port range is open in firewall
sudo ufw allow 8000:9000/tcp
```

## Security Considerations

### What Makes This Secure

1. **Multi-layer Defense**: 5 different bypass methods
2. **Traffic Encryption**: All data is encrypted
3. **Pattern Obfuscation**: Traffic looks like normal web browsing
4. **Dynamic Ports**: Constantly changing endpoints
5. **Legitimate Fronting**: Uses real CDN services

### Operational Security

- **Regular Updates**: Keep bypass methods updated
- **Log Monitoring**: Watch for connection patterns
- **Backup Methods**: Always have multiple options ready
- **Credential Rotation**: Change passwords regularly

## Performance Tips

### Optimize for Speed

```bash
# Reduce hop interval for faster switching
export HOP_INTERVAL=120  # 2 minutes

# Use fewer obfuscation layers for speed
export LITE_OBFUSCATION=true
```

### Optimize for Stealth

```bash
# Increase hop interval for stealth
export HOP_INTERVAL=600  # 10 minutes

# Enable maximum obfuscation
export MAX_OBFUSCATION=true
```

## Regional Considerations

### High-Censorship Regions

- Enable all bypass methods
- Use domain fronting heavily
- Rotate credentials frequently
- Monitor connection success rates

### Moderate-Censorship Regions  

- Port hopping usually sufficient
- HTTP tunnel as backup
- Monitor for blocking patterns

### Low-Censorship Regions

- Direct connection usually works
- Keep bypass methods as backup
- Focus on performance over stealth

## Support

### Getting Help

1. Check logs: `tail -f bypass-server.log`
2. Test connection: `python3 src/bypass_client.py`
3. Verify main proxy: `python3 test-proxy.py --local`
4. Check firewall: `netstat -tlnp | grep 8443`

### Emergency Fallback

If all methods fail:

1. Change server IP
2. Use different ports entirely  
3. Deploy on different cloud provider
4. Use VPN + proxy combination

---

## Summary

Your Telegram SOCKS5 proxy now has **5 layers of anti-blocking protection**:

**Port Hopping** - Evades port blocking  
**HTTP Tunnel** - Bypasses DPI  
**WebSocket** - Looks like chat apps  
**Domain Fronting** - Uses legitimate CDNs  
**Traffic Obfuscation** - Hides patterns  

**Start bypass protection**: `./start-bypass.sh`  
**Test connection**: `python3 src/bypass_client.py`  
**Stop bypass**: `./stop-bypass.sh`

Your proxy is now **highly resistant to blocking attempts**!
