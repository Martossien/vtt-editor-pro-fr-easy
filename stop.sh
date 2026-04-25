#!/usr/bin/env bash
set -euo pipefail
# ──────────────────────────────────────────────
# SRT Editor Pro — Arrêt du serveur
# Usage: ./stop.sh [--force]
# ──────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="$SCRIPT_DIR/.server.pid"
LOG_FILE="$SCRIPT_DIR/.server.log"
FORCE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --force|-f) FORCE=true; shift ;;
        *) echo "Option inconnue: $1"; exit 1 ;;
    esac
done

if [[ ! -f "$PID_FILE" ]]; then
    echo "ℹ️  Aucun fichier PID trouvé (le serveur n'est probablement pas lancé via start.sh)"

    # Chercher le processus autrement
    PIDS=$(pgrep -f "python3 server.py" 2>/dev/null || true)
    if [[ -n "$PIDS" ]]; then
        echo "   Processus trouvés: $PIDS"
        echo "   Pour les arrêter: kill $PIDS"
    fi
    exit 0
fi

SERVER_PID=$(cat "$PID_FILE")

if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "ℹ️  Le processus PID $SERVER_PID n'existe plus (déjà arrêté ?)"
    rm -f "$PID_FILE"
    exit 0
fi

echo "🛑 Arrêt du serveur (PID $SERVER_PID)..."

if $FORCE; then
    kill -9 "$SERVER_PID" 2>/dev/null || true
    echo "   Arrêt forcé (SIGKILL)"
else
    kill "$SERVER_PID" 2>/dev/null || true

    # Attendre l'arrêt gracieux
    for i in {1..10}; do
        if ! kill -0 "$SERVER_PID" 2>/dev/null; then
            break
        fi
        sleep 0.5
    done

    # Si toujours vivant, forcer
    if kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "   Le processus ne répond pas, arrêt forcé..."
        kill -9 "$SERVER_PID" 2>/dev/null || true
    fi
fi

rm -f "$PID_FILE"
echo "✅ Serveur arrêté"

# Afficher les dernières lignes de log si le fichier existe
if [[ -f "$LOG_FILE" ]]; then
    echo ""
    echo "📋 Dernières lignes de log :"
    echo "─────────────────────────────"
    tail -5 "$LOG_FILE"
fi
