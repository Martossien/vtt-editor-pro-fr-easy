#!/usr/bin/env bash
set -euo pipefail
# ──────────────────────────────────────────────
# SRT Editor Pro — État du serveur
# Usage: ./status.sh [--watch] [--logs]
# ──────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="$SCRIPT_DIR/.server.pid"
LOG_FILE="$SCRIPT_DIR/.server.log"
PORT="${PORT:-7861}"
WATCH=false
SHOW_LOGS=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --watch|-w) WATCH=true; shift ;;
        --logs|-l) SHOW_LOGS=true; shift ;;
        *) echo "Option inconnue: $1"; exit 1 ;;
    esac
done

# ── Fonctions ──────────────────────────────

print_separator() {
    echo "──────────────────────────────────────────────────────────"
}

check_port() {
    # Vérifier si le port est utilisé
    local port_listener
    port_listener=$(lsof -ti:"$PORT" 2>/dev/null || true)
    if [[ -n "$port_listener" ]]; then
        echo "✅ Port $PORT : occupé (PID $port_listener)"
        return 0
    else
        echo "❌ Port $PORT : libre (aucun processus n'écoute)"
        return 1
    fi
}

check_pid_file() {
    if [[ ! -f "$PID_FILE" ]]; then
        echo "⚠️  Fichier PID : absent"
        return 1
    fi
    local pid
    pid=$(cat "$PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
        echo "✅ Fichier PID : présent (PID $pid vivant)"
        return 0
    else
        echo "⚠️  Fichier PID : présent mais PID $pid est mort (fichier obsolète)"
        return 1
    fi
}

check_process() {
    local pids
    pids=$(pgrep -f "python3 server.py" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        echo "✅ Processus server.py :"
        for pid in $pids; do
            local mem cpu
            mem=$(ps -o rss= -p "$pid" 2>/dev/null | awk '{printf "%.1f MB", $1/1024}')
            cpu=$(ps -o %cpu= -p "$pid" 2>/dev/null || echo "?")
            local uptime
            uptime=$(ps -o etime= -p "$pid" 2>/dev/null | xargs || echo "?")
            echo "   PID $pid — CPU: ${cpu}% — RAM: ${mem:-?} — Uptime: ${uptime:-?}"
        done
        return 0
    else
        echo "❌ Processus server.py : aucun trouvé"
        return 1
    fi
}

check_api() {
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/api/session" 2>/dev/null || echo "000")
    if [[ "$http_code" == "200" ]]; then
        local session
        session=$(curl -s "http://localhost:$PORT/api/session" 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
pid=d.get('project_id','-')
cues=len(d.get('cues',[]))
print(f'Projet: {pid}  |  Segments: {cues}')" 2>/dev/null || echo "?")
        echo "✅ API /api/session : HTTP $http_code — $session"
        return 0
    else
        echo "❌ API /api/session : HTTP $http_code (serveur injoignable ?)"
        return 1
    fi
}

show_general_status() {
    local overall="✅ RUNNING"
    local pid
    pid=$(cat "$PID_FILE" 2>/dev/null || echo "?")
    if ! kill -0 "$pid" 2>/dev/null; then
        overall="❌ STOPPED"
    fi

    echo ""
    echo "  🎵 SRT Editor Pro — $overall"
    echo ""
    print_separator
    check_pid_file
    check_process
    print_separator
    check_port
    print_separator
    check_api
    print_separator

    # Logs
    if [[ -f "$LOG_FILE" ]]; then
        local log_size
        log_size=$(du -h "$LOG_FILE" 2>/dev/null | cut -f1)
        echo "📋 Fichier log : $LOG_FILE ($log_size)"
        print_separator
        echo ""
        echo "Dernières 10 lignes :"
        tail -10 "$LOG_FILE"
    else
        echo "📋 Fichier log : absent"
    fi
    echo ""
    echo "Commandes utiles :"
    echo "  ./start.sh              Démarrer le serveur"
    echo "  ./stop.sh               Arrêter le serveur"
    echo "  ./status.sh --watch     Surveillance en temps réel"
    echo "  ./status.sh --logs      Suivre les logs (tail -f)"
    echo "  curl localhost:$PORT/api/debug/logs  Logs debug JSON"
    echo ""
}

# ── Mode watch ──────────────────────────────

if $WATCH; then
    echo "👀 Surveillance du serveur SRT Editor Pro (Ctrl+C pour quitter)"
    echo ""
    while true; do
        clear 2>/dev/null || true
        show_general_status
        sleep 3
    done
fi

# ── Mode logs ───────────────────────────────

if $SHOW_LOGS; then
    if [[ -f "$LOG_FILE" ]]; then
        echo "📋 Suivi des logs en temps réel (Ctrl+C pour quitter)"
        echo "   Fichier: $LOG_FILE"
        echo ""
        exec tail -f "$LOG_FILE"
    else
        echo "❌ Aucun fichier de log trouvé ($LOG_FILE)"
        echo "   Le serveur n'a probablement pas été lancé via ./start.sh"
        exit 1
    fi
fi

# ── Mode par défaut : affichage unique ───────

show_general_status
