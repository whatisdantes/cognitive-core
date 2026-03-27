# ============================================================
# Dockerfile — cognitive-core v0.7.0
# Multi-stage build + non-root user (P1-E11)
# ============================================================

# --- Stage 1: Builder ---
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /build

# Копируем только файлы зависимостей для кэширования слоя
COPY pyproject.toml README.md LICENSE ./
COPY brain/ ./brain/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# --- Stage 2: Runtime ---
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Создаём non-root пользователя
RUN groupadd --gid 1000 brain && \
    useradd --uid 1000 --gid brain --create-home brain

# Копируем установленные пакеты из builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/cognitive-core /usr/local/bin/cognitive-core

# Копируем исходный код (для data/ директории)
WORKDIR /app
COPY --chown=brain:brain brain/ ./brain/

# Создаём директорию для данных памяти
RUN mkdir -p /app/brain/data/memory && \
    chown -R brain:brain /app/brain/data

# Переключаемся на non-root пользователя
USER brain

ENTRYPOINT ["cognitive-core"]
CMD ["Что такое нейропластичность?"]
