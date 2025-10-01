#!/bin/bash

# THEIA Interview Prep System - Full System Startup
# This script starts both backend and frontend services

echo "🚀 Starting THEIA Interview Prep System - Full Stack"
echo "=================================================="

# Check if we're in the right directory
if [ ! -f "backend/simple_main.py" ]; then
    echo "❌ Error: Please run this script from the project root directory"
    exit 1
fi

# Function to check if a port is in use
check_port() {
    lsof -i :$1 > /dev/null 2>&1
    return $?
}

# Function to free a port (SIGTERM then SIGKILL fallback)
free_port() {
    PORT=$1
    NAME=$2
    PIDS=$(lsof -ti tcp:${PORT} 2>/dev/null || true)
    if [ -n "$PIDS" ]; then
        echo "🔪 Freeing ${NAME} on port ${PORT} (PIDs: $PIDS)"
        kill -15 $PIDS >/dev/null 2>&1 || true
        sleep 1
        # If still busy, force kill
        STILL=$(lsof -ti tcp:${PORT} 2>/dev/null || true)
        if [ -n "$STILL" ]; then
            echo "⚠️  Port ${PORT} still busy; sending SIGKILL"
            kill -9 $STILL >/dev/null 2>&1 || true
            sleep 1
        fi
        # Final check
        if check_port ${PORT}; then
            echo "❌ Could not free port ${PORT}. You may need to run manually: kill -9 $PIDS"
        else
            echo "✅ ${NAME} port ${PORT} is now free"
        fi
    else
        echo "✅ ${NAME} port ${PORT} is already free"
    fi
}

# Allow overriding backend port; default to 8010 for uvicorn
THEIA_BACKEND_PORT="${THEIA_BACKEND_PORT:-8010}"

# Proactively free dev ports unless opted out
if [ -z "$THEIA_SKIP_PORT_CLEAN" ]; then
    echo "🧹 Cleaning dev ports (${THEIA_BACKEND_PORT} backend, 8002 analyzer, 3000 frontend)"
    free_port ${THEIA_BACKEND_PORT} "THEIA Backend"
    free_port 8002 "Interview Analyzer"
    free_port 3000 "THEIA Frontend"
else
    echo "⏭️  Skipping port cleanup (THEIA_SKIP_PORT_CLEAN=1)"
fi

# Start Backend
echo "🔧 Starting THEIA Backend (FastAPI on ${THEIA_BACKEND_PORT})..."
if check_port ${THEIA_BACKEND_PORT}; then
    echo "✅ Backend already running on port ${THEIA_BACKEND_PORT}"
else
    VENV_PATH="/Users/fernandoponce/interviewAnalyzer/.venv"
    if [ ! -x "$VENV_PATH/bin/python" ]; then
        echo "❌ Provided venv not found at $VENV_PATH"
        echo "   Please create it (python3 -m venv $VENV_PATH) and install requirements, then re-run."
        exit 1
    fi
    echo "📦 Using Python virtual environment: $VENV_PATH"
    # Optionally ensure THEIA backend requirements are present in the shared venv
    REQ_FILE=""
    if [ -f "../requirements.txt" ]; then
        REQ_FILE="../requirements.txt"
    elif [ -f "../../requirements.txt" ]; then
        REQ_FILE="../../requirements.txt"
    fi
    if [ -n "$REQ_FILE" ]; then
        echo "📦 Installing backend requirements into shared venv (from $REQ_FILE)..."
        "$VENV_PATH/bin/pip" install --upgrade pip setuptools wheel >/dev/null 2>&1 || true
        "$VENV_PATH/bin/pip" install -r "$REQ_FILE" || echo "⚠️  Some backend requirements may be missing"
    fi
    echo "📦 Activating Python virtual environment..."
    # shellcheck disable=SC1090
    source "$VENV_PATH/bin/activate"
    
    echo "🌟 Starting FastAPI backend with uvicorn on port ${THEIA_BACKEND_PORT}..."
    cd backend
    python -m uvicorn simple_main:app --host 0.0.0.0 --port ${THEIA_BACKEND_PORT} &
    BACKEND_PID=$!
    echo "✅ Backend started (PID: $BACKEND_PID) on http://localhost:${THEIA_BACKEND_PORT}"
    cd ..
fi

# Wait for backend to be ready
echo "⏳ Waiting for backend to be ready..."
sleep 3

# Test backend
if curl -s http://localhost:${THEIA_BACKEND_PORT}/health > /dev/null; then
    echo "✅ Backend is responding"
else
    echo "❌ Backend is not responding"
fi

# Start Interview Analyzer (parent repo) on port 8002
echo ""
echo "🧩 Starting Interview Analyzer Backend (FastAPI) on 8002..."
if check_port 8002; then
    echo "✅ Interview Analyzer already running on port 8002"
else
    # Detect Interview Analyzer root from one or two levels up
    if [ -f "../app/main.py" ]; then
        IA_DIR="$(cd .. && pwd)"
    elif [ -f "../../app/main.py" ]; then
        IA_DIR="$(cd ../.. && pwd)"
    else
        IA_DIR="$(cd ../.. && pwd)"
    fi
    if [ -f "$IA_DIR/app/main.py" ]; then
        # Load Interview Analyzer environment variables from its .env (if present)
        if [ -f "$IA_DIR/.env" ]; then
            echo "🔑 Loading Interview Analyzer environment from $IA_DIR/.env"
            set -a
            . "$IA_DIR/.env"
            set +a
        else
            echo "⚠️  No .env found at $IA_DIR/.env; proceeding without env injection"
        fi

        echo "📦 Preparing isolated venv for Interview Analyzer..."
        IA_VENV="$IA_DIR/.venv"
        if [ ! -d "$IA_VENV" ]; then
            if command -v python3 >/dev/null 2>&1; then
                python3 -m venv "$IA_VENV" || echo "❌ Failed to create venv at $IA_VENV"
            elif command -v python >/dev/null 2>&1; then
                python -m venv "$IA_VENV" || echo "❌ Failed to create venv at $IA_VENV"
            fi
            if [ -x "$IA_VENV/bin/pip" ]; then
                "$IA_VENV/bin/pip" install --upgrade pip setuptools wheel >/dev/null 2>&1 || true
                "$IA_VENV/bin/pip" install -r "$IA_DIR/requirements.txt" || echo "❌ Failed to install Interview Analyzer requirements"
            else
                echo "❌ No pip available in $IA_VENV; cannot install requirements."
            fi
        fi

        START_CMD=""
        if [ -x "$IA_VENV/bin/python" ]; then
            START_CMD="\"$IA_VENV/bin/python\" -m uvicorn app.main:app --host 0.0.0.0 --port 8002"
        elif command -v python3 >/dev/null 2>&1; then
            START_CMD="python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8002"
        elif command -v python >/dev/null 2>&1; then
            START_CMD="python -m uvicorn app.main:app --host 0.0.0.0 --port 8002"
        fi

        if [ -n "$START_CMD" ]; then
            (
              cd "$IA_DIR" && \
              eval $START_CMD &
            ) || echo "❌ Failed to launch Interview Analyzer with: $START_CMD"
            IA_PID=$!
            echo "⏳ Waiting for Interview Analyzer on http://localhost:8002/healthz"
            for i in $(seq 1 20); do
                if curl -s http://localhost:8002/healthz >/dev/null; then
                    echo "✅ Interview Analyzer is responding"
                    break
                fi
                sleep 1
            done
            if ! curl -s http://localhost:8002/healthz >/dev/null; then
                echo "❌ Interview Analyzer failed to start on 8002. Try manually: (cd \"$IA_DIR\" && $START_CMD)"
            else
                echo "✅ Interview Analyzer started (PID: $IA_PID) on http://localhost:8002"
            fi
        else
            echo "❌ Could not find a suitable Python to start Interview Analyzer. Skipping."
        fi
    else
        echo "⚠️  Interview Analyzer not found at $IA_DIR; skipping."
    fi
fi

# Start Frontend
echo ""
echo "🎨 Starting THEIA Frontend (React SPA)..."
# Ensure frontend does not inherit PORT from .env (used by backend)
unset PORT 2>/dev/null || true
if check_port 3000; then
    echo "✅ Frontend already running on port 3000"
else
    echo "📦 Starting React development server..."
    cd frontend/theia-frontend
    HOST=localhost PORT=3000 npm start &
    FRONTEND_PID=$!
    echo "✅ Frontend started (PID: $FRONTEND_PID) on http://localhost:3000"
    cd ../..

    # Attempt to open the SPA root in the default browser
    echo "🌐 Opening THEIA App in your browser (http://localhost:3000)"
    if command -v open >/dev/null 2>&1; then
        open "http://localhost:3000" >/dev/null 2>&1 || true
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "http://localhost:3000" >/dev/null 2>&1 || true
    fi
fi

echo ""
echo "🎉 THEIA Interview Prep System is starting up!"
echo "=================================================="
echo "📡 Backend API:  http://localhost:${THEIA_BACKEND_PORT}"
echo "🧩 Jobs API:    http://localhost:8002"
echo "🎨 Frontend UI:  http://localhost:3000"
echo "📚 API Docs:     http://localhost:8000/docs"
echo "🏥 Health Check: http://localhost:8000/test/credentials"
echo ""
echo "⏳ Frontend may take 30-60 seconds to fully load..."
echo "🌐 Open http://localhost:3000 in your browser"
echo ""
echo "Press Ctrl+C to stop all services"

# Keep script running
wait


