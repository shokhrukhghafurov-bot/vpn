FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV XRAY_BIN=/usr/local/bin/xray

WORKDIR /app

# Системные пакеты
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    unzip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Установка Xray
RUN ARCH="$(uname -m)" && \
    case "$ARCH" in \
      x86_64) XRAY_ARCH="64" ;; \
      aarch64|arm64) XRAY_ARCH="arm64-v8a" ;; \
      *) echo "Unsupported arch: $ARCH" && exit 1 ;; \
    esac && \
    curl -L -o /tmp/xray.zip "https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-${XRAY_ARCH}.zip" && \
    unzip /tmp/xray.zip -d /tmp/xray && \
    install -m 0755 /tmp/xray/xray /usr/local/bin/xray && \
    rm -rf /tmp/xray /tmp/xray.zip

# Проверка, что бинарь установлен
RUN /usr/local/bin/xray version

# Python зависимости
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Код приложения
COPY . /app

# Railway даёт PORT через env
CMD sh -c "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"
