FROM rust:1.99.0-slim-bookworm AS rust-toolchain

FROM python:3.12.12-slim AS native-builder
COPY --from=rust-toolchain /usr/local/cargo /usr/local/cargo
COPY --from=rust-toolchain /usr/local/rustup /usr/local/rustup
ENV PATH=/usr/local/cargo/bin:$PATH RUSTUP_HOME=/usr/local/rustup CARGO_HOME=/usr/local/cargo
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*
COPY server/native /native
RUN pip wheel --no-cache-dir --no-deps /native --wheel-dir /wheels

FROM python:3.12.12-slim
WORKDIR /app
COPY --from=native-builder /wheels /wheels
COPY server /app/server
RUN pip install --no-cache-dir /wheels/*.whl ./server[server] && rm -rf /wheels /app/server/native && useradd -u 10001 -m singularity && mkdir /state && chown singularity /state
USER singularity
ENV PYTHONUNBUFFERED=1 STATE_DIR=/state
CMD ["uvicorn", "singularity.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers", "--no-access-log"]
