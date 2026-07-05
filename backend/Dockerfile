FROM python:3.11-slim@sha256:b27df5841f3355e9473f9a516d38a6783b6c8dfeacaf2d14a240f443b368ddb6 AS base

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose backend port
EXPOSE 9000

# Default: run the startup script (handles DB wait + schema init)
# Hardening (#122): never write bytecode (read-only rootfs friendly) and run as an
# explicit non-root user — created here, switched BEFORE the entrypoint.
ENV PYTHONDONTWRITEBYTECODE=1
RUN useradd --create-home --uid 10001 appuser
USER 10001

ENTRYPOINT ["/app/start.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
