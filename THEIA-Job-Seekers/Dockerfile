# Use Python 3.11 slim image for ASGI compatibility
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy root requirements and install Python dependencies (build context is repo root)
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code from external directory
COPY external/THEIA-Job-Seekers/backend/ ./backend/
COPY external/THEIA-Job-Seekers/credentials/ ./credentials/
COPY external/THEIA-Job-Seekers/main.py ./main.py

# Create logs directory
RUN mkdir -p logs

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Expose the port
EXPOSE 8080

# Run the application with explicit ASGI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
