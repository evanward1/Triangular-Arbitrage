# Multi-stage Docker build for triangular arbitrage system
# Use slim Python 3.11 base for smaller image size
FROM python:3.11-slim as base

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
COPY requirements.txt requirements-dev.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements-dev.txt

# Copy the entire repository
COPY . .

# Install the application in development mode
RUN pip install -e .

# Change ownership to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Expose metrics port
EXPOSE 8000

# Default command runs tests
CMD ["python", "-m", "pytest", "tests/", "-v"]

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

# Remove development dependencies to minimize size
RUN pip uninstall -y pytest pytest-cov mypy black isort flake8 pre-commit

# Production command runs the strategy
CMD ["python", "run_strategy.py", "--help"]
