FROM python:3.11

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# In the container, the otel startup complains about psycopg2 but it doesn't seem to be an issue for local dev!
# Install Python dependencies
RUN pip install -r requirements.txt

# Copy application code
COPY main.py .

# # Create a non-root user for security
# RUN adduser --disabled-password --gecos '' --uid 1000 appuser && \
#     chown -R appuser:appuser /app
# USER appuser

# Expose the port that uvicorn will run on
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost/ || exit 1
    # CMD python -c "import requests; requests.get('http://localhost:8000/ping')" || exit 1

# Command to run the application
ENV OTEL_PYTHON_DISABLED_INSTRUMENTATIONS="psycopg2" 
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]