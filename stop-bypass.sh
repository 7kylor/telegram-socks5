#!/bin/bash

# Stop Bypass Server for Telegram SOCKS5 Proxy

LOG_FILE="bypass.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

info() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: $1" | tee -a "$LOG_FILE"
}

stop_bypass_server() {
    log "Stopping bypass server..."
    
    # Stop bypass server using PID file
    if [[ -f "bypass-server.pid" ]]; then
        BYPASS_PID=$(cat bypass-server.pid)
        if kill -0 $BYPASS_PID 2>/dev/null; then
            log "Stopping bypass server (PID: $BYPASS_PID)..."
            kill $BYPASS_PID
            
            # Wait for graceful shutdown
            for i in {1..10}; do
                if ! kill -0 $BYPASS_PID 2>/dev/null; then
                    break
                fi
                sleep 1
            done
            
            # Force kill if still running
            if kill -0 $BYPASS_PID 2>/dev/null; then
                log "Force stopping bypass server..."
                kill -9 $BYPASS_PID 2>/dev/null || true
            fi
            
            log "Bypass server stopped"
        else
            log "Bypass server was not running"
        fi
        
        rm -f bypass-server.pid
    else
        log "No PID file found, checking for running processes..."
        
        # Find and kill any running bypass server processes
        PIDS=$(pgrep -f "bypass_server.py" || true)
        if [[ -n "$PIDS" ]]; then
            log "Found running bypass server processes: $PIDS"
            echo "$PIDS" | xargs kill 2>/dev/null || true
            sleep 2
            echo "$PIDS" | xargs kill -9 2>/dev/null || true
            log "Bypass server processes stopped"
        else
            log "No bypass server processes found"
        fi
    fi
}

cleanup_files() {
    log "Cleaning up temporary files..."
    
    # Clean up log files (keep recent ones)
    if [[ -f "bypass-server.log" ]]; then
        tail -n 1000 bypass-server.log > bypass-server.log.tmp
        mv bypass-server.log.tmp bypass-server.log
    fi
    
    log "Cleanup completed"
}

show_status() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════════════════╗"
    echo "║                        BYPASS SERVER STOPPED                                 ║"
    echo "╚══════════════════════════════════════════════════════════════════════════════╝"
    echo ""
    echo " STATUS:"
    echo "┌─────────────────────────────────────────────────────────────────────────────┐"
    echo "│    Bypass server: STOPPED"
    echo "│    Port hopping: DISABLED"
    echo "│    HTTP tunnel: DISABLED"
    echo "│    WebSocket tunnel: DISABLED"
    echo "│    Domain fronting: DISABLED"
    echo "└─────────────────────────────────────────────────────────────────────────────┘"
    echo ""
    echo " MAIN PROXY STATUS:"
    if docker ps | grep -q "telegram-socks5.*Up"; then
        echo "    Main SOCKS5 proxy is still running"
        echo "    Direct connection still available"
    else
        echo "    Main SOCKS5 proxy is not running"
    fi
    echo ""
    echo " RESTART BYPASS:"
    echo "   ./start-bypass.sh"
    echo ""
}

main() {
    echo ""
    echo "=================================================="
    echo "  Stopping Telegram SOCKS5 Bypass Server"
    echo "=================================================="
    echo ""
    
    stop_bypass_server
    cleanup_files
    show_status
    
    log "Bypass server shutdown completed"
}

# Run main function
main "$@" 