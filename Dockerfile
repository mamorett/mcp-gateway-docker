FROM python:3.12-slim-bookworm

# 1. Installazione UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 2. Tool di base + Node.js + GIT (Finalmente!)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg dnsutils procps net-tools git \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update && apt-get install -y nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Forziamo i log immediati
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Installazione librerie core del gateway
RUN uv pip install --system mcp==1.2.1 starlette uvicorn

COPY gateway.py .

EXPOSE 8080

CMD ["python3", "gateway.py"]