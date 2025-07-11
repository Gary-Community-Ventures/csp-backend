# Use Python 3.11 slim image for smaller size
# Please keep version same as .python_version used for defining Heroku python version
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=wsgi.py \  
    FLASK_ENV=development 

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN adduser --disabled-password --gecos '' appuser

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

USER appuser

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Default command for development (overridden by docker-compose for hot reload)
# This CMD is primarily for standalone `docker run` or production Gunicorn.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "wsgi:app"] # <--- Use wsgi.py for Gunicorn
