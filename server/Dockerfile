FROM python:3.12.12-slim
WORKDIR /app
COPY server /app/server
RUN pip install --no-cache-dir ./server[server] && useradd -u 10001 -m singularity && mkdir /state && chown singularity /state
USER singularity
ENV PYTHONUNBUFFERED=1 STATE_DIR=/state
CMD ["uvicorn", "singularity.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers", "--no-access-log"]
