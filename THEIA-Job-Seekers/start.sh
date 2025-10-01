#!/bin/bash

# THEIA Interview Prep System - Startup Script
# This script starts the backend server for local development

echo "🚀 Starting THEIA Interview Prep System..."

# Check if we're in the right directory
if [ ! -f "backend/main.py" ]; then
    echo "❌ Error: Please run this script from the project root directory"
    exit 1
fi

# Check if Python virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  Warning: .env file not found. Copying from env.example..."
    cp env.example .env
    echo "📝 Please edit .env file with your actual credentials before running the server"
fi

# Check if Redis is running
echo "🔍 Checking Redis connection..."
redis-cli ping > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "⚠️  Warning: Redis is not running. Please start Redis server:"
    echo "   macOS: brew services start redis"
    echo "   Linux: sudo systemctl start redis"
    echo "   Docker: docker run -d -p 6379:6379 redis:alpine"
fi

# Start the FastAPI server
echo "🌟 Starting FastAPI server..."
echo "📡 Server will be available at: http://localhost:8000"
echo "📚 API documentation at: http://localhost:8000/docs"
echo "🏥 Health check at: http://localhost:8000/health"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000


