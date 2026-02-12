FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
RUN pip install --no-cache-dir uv

# Copy dependency files (including lock file for reproducible installs)
COPY pyproject.toml uv.lock ./

# Export pinned requirements from lock file, then install system-wide
RUN uv export --frozen --no-dev --no-editable --no-hashes -o requirements.txt && \
    uv pip install --system --no-cache -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
