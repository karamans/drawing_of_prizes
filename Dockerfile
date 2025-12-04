FROM python:3.13-slim

WORKDIR /app

# Install system dependencies required for building C extensions (TgCrypto)
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ src/
COPY auth.py .
COPY src/config.py src/

# We don't copy .env or data/ because they are mounted/created at runtime
# But we need to make sure data dir exists
RUN mkdir -p data

# Command to run the bot
CMD ["python", "-m", "src.bot"]

