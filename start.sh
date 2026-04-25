#!/usr/bin/env bash
set -euo pipefail
# ──────────────────────────────────────────────
# SRT Editor Pro — Démarrage du serveur
# Usage: ./start.sh [--port 7861] [--debug] [--foreground]
# ──────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="$SCRIPT_DIR/.server.pid"
LOG_FILE="$SCRIPT_DIR/.server.log"
PORT="${PORT:-7861}"
FOREGROUND=false
DEBUG_FLAG="--debug"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --port) PORT="$2"; shift 2 ;;
        --debug) DEBUG_FLAG="--debug"; shift ;;
        --foreground|-f) FOREGROUND=true; shift ;;
        *) echo "Option inconnue: $1"; exit 1 ;;
    esac
done

# Vérifier si déjà lancé
if [[ -f "$PID_FILE" ]]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "❌ Serveur déjà en cours d'exécution (PID $OLD_PID, port $PORT)"
        echo "   Utilisez ./stop.sh pour l'arrêter, ou ./status.sh pour voir l'état"
        exit 1
    else
        echo "⚠️  Ancien fichier PID trouvé (PID $OLD_PID n'existe plus), nettoyage..."
        rm -f "$PID_FILE"
    fi
fi

# Vérifier que le port est libre
PORT_PID=$(lsof -ti:"$PORT" 2>/dev/null || true)
if [[ -n "$PORT_PID" ]]; then
    PORT_PROC=$(ps -o comm= -p "$PORT_PID" 2>/dev/null || echo "?")
    echo "❌ Le port $PORT est déjà occupé par PID $PORT_PID ($PORT_PROC)"
    echo "   Arrêtez ce processus ou utilisez un autre port :"
    echo "   ./start.sh --port 7862"
    exit 1
fi

# Vérifier que Flask est disponible
if ! python3 -c "import flask" 2>/dev/null; then
    echo "📦 Installation de Flask..."
    pip install flask -q
fi

echo "🚀 Démarrage de SRT Editor Pro..."
echo "   Port    : $PORT"
echo "   Debug   : $DEBUG_FLAG"
echo "   Log     : $LOG_FILE"
echo "   PID     : $PID_FILE"

if $FOREGROUND; then
    # Mode foreground : affiche les logs directement
    echo "   Mode    : foreground (Ctrl+C pour arrêter)"
    echo ""
    exec python3 server.py --port "$PORT" $DEBUG_FLAG
else
    # Mode background
    nohup python3 server.py --port "$PORT" $DEBUG_FLAG > "$LOG_FILE" 2>&1 &
    SERVER_PID=$!
    echo "$SERVER_PID" > "$PID_FILE"

    # Attendre que le serveur démarre
    echo -n "⏳ Attente du démarrage"
    for i in {1..15}; do
        if curl -s -o /dev/null "http://localhost:$PORT/" 2>/dev/null; then
            echo ""
            echo "✅ Serveur démarré avec succès (PID $SERVER_PID)"
            echo "   URL: http://localhost:$PORT/"
            echo "   Logs: tail -f $LOG_FILE"
            echo "   Status: ./status.sh"
            echo "   Arrêt: ./stop.sh"
            exit 0
        fi
        echo -n "."
        sleep 0.5
    done

    echo ""
    # Vérifier si le processus est toujours vivant
    if kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "⚠️  Serveur lancé mais ne répond pas encore sur le port $PORT"
        echo "   Vérifiez les logs: tail -f $LOG_FILE"
    else
        echo "❌ Le serveur n'a pas démarré. Dernières lignes de log :"
        tail -20 "$LOG_FILE"
        rm -f "$PID_FILE"
        exit 1
    fi
fi
