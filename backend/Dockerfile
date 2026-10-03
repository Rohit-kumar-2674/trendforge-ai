FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock && useradd --create-home --uid 10001 trendforge
COPY backend /app/backend
RUN pip install --no-deps /app/backend && mkdir -p /app/data /app/reports && chown -R trendforge:trendforge /app
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/system/health', timeout=4)"
CMD ["sh", "-c", "trendforge update && exec trendforge serve --host 0.0.0.0"]
