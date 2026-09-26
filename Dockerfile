# ФинРитм API. Сборка: docker build -t finritm .  Запуск: docker compose up --build
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=prod \
    DATABASE_PATH=/app/runtime/finritm.sqlite3

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# core читает data/demo и contracts/ относительно корня /app
COPY backend/ backend/
COPY contracts/ contracts/
COPY data/ data/

RUN useradd --create-home --uid 1000 app && mkdir -p /app/runtime && chown app /app/runtime
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request, os; urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\", \"8000\")}/api/health')"

# PORT задают некоторые хостинги (Render и др.); по умолчанию 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --app-dir backend --proxy-headers"]
