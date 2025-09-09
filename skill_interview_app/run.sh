#!/bin/bash

# Skill Interview App Run Script

echo "🚀 Starting AI Skill Interview App..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install/update dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found. Copying from .env.example..."
    cp .env.example .env
    echo "✏️  Please edit .env file with your actual credentials before running the app."
    exit 1
fi

# Run the application
echo "🌐 Starting server on http://localhost:8001"
echo "📊 API docs available at http://localhost:8001/docs"
echo "Press Ctrl+C to stop the server"
echo ""

python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8001