# Use a stable Python runtime
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install system dependencies (C compiler and common libs)
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Ensure latest pip/setuptools/wheel are available, then install dependencies
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code into the container
COPY . .

# Command to run your application (use Render's PORT if available)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]