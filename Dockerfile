FROM python:3.11-alpine

# Security: Create non-root user
RUN addgroup -g 1001 -S proxyuser && \
    adduser -u 1001 -S proxyuser -G proxyuser

# Install required packages with minimal attack surface
RUN apk add --no-cache \
    tini \
    openssl \
    ca-certificates \
    iptables \
    && rm -rf /var/cache/apk/*

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install build dependencies, install Python packages, then remove build deps
RUN apk add --no-cache --virtual .build-deps \
    gcc \
    musl-dev \
    python3-dev \
    linux-headers \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps

# Copy application code
COPY src/ ./src/
COPY config/ ./config/

# Set permissions
RUN chown -R proxyuser:proxyuser /app
RUN chmod +x /app/src/main.py

# Security: Drop privileges
USER proxyuser

# Health check - less aggressive to avoid rate limiting
HEALTHCHECK --interval=45s --timeout=15s --start-period=10s --retries=3 \
    CMD python /app/src/health_check.py || exit 1

# Use tini as init system
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["python", "/app/src/main.py"]

# Expose SOCKS5 port
EXPOSE 1080

# Security labels
LABEL security.non-root=true
LABEL security.minimal=true 