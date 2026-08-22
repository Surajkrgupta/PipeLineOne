FROM python:3.11-slim-bookworm

WORKDIR /app

# System dependencies for Playwright's Chromium (fonts, graphics libs) --
# this is exactly what failed on Render's native buildpack (no root access
# there). A Docker build has full root access during the build step, so
# --with-deps works cleanly here.
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium + its system dependencies as root (build stage)
RUN playwright install --with-deps chromium

COPY . .

# Render (and most PaaS) inject $PORT at runtime -- bind to it
ENV PORT=8000
EXPOSE 8000

CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT