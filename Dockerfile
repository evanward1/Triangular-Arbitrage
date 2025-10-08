# Multi-stage Docker build for triangular arbitrage system with web dashboard

# Stage 1: Build React frontend
FROM node:18-alpine AS frontend-builder

WORKDIR /app/web_ui
COPY web_ui/package*.json ./
RUN npm install
COPY web_ui/ ./
RUN npm run build

# Stage 2: Python backend
FROM python:3.10-slim as base

# Install system dependencies required for the application
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set up working directory
WORKDIR /app

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy requirements first for better Docker layer caching
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire repository
COPY . .

# Copy built React frontend from builder stage
COPY --from=frontend-builder /app/web_ui/build /app/web_ui/build

# Install the application in development mode
RUN pip install -e .

# Create logs directory
RUN mkdir -p logs

# Change ownership to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV TRADING_MODE=paper

# Expose web server port
EXPOSE 8000

# Default command runs the web server
CMD ["python", "web_server.py"]

# Development stage with additional tools
FROM base as dev

# Switch back to root to install additional dev tools
USER root

# Install additional development utilities
RUN apt-get update && apt-get install -y \
    vim \
    htop \
    && rm -rf /var/lib/apt/lists/*

USER appuser

# Development command launches interactive shell
CMD ["/bin/bash"]

# Production stage - minimal runtime
FROM base as prod

# Production command runs the web server
CMD ["python", "web_server.py"]
