FROM python:3.14-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /workspace

ARG PIP_PROXY=""
COPY contracts ./contracts
COPY src/signal-ml ./src/signal-ml
RUN --mount=type=cache,target=/root/.cache/pip \
    if [ -n "$PIP_PROXY" ]; then \
        python -m pip --proxy "$PIP_PROXY" install "grpcio-tools>=1.81,<1.82"; \
    else \
        python -m pip install "grpcio-tools>=1.81,<1.82"; \
    fi \
    && python src/signal-ml/scripts/generate_grpc.py \
    && if [ -n "$PIP_PROXY" ]; then \
        python -m pip --proxy "$PIP_PROXY" wheel --wheel-dir /wheels './src/signal-ml[grpc]'; \
    else \
        python -m pip wheel --wheel-dir /wheels './src/signal-ml[grpc]'; \
    fi

FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    ML_GRPC_HOST=0.0.0.0 \
    ML_GRPC_PORT=50051
WORKDIR /app

COPY --from=build /wheels /wheels
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels \
        'crypto-ml-signal[grpc]==0.3.0' \
    && rm -rf /wheels
COPY src/signal-ml/artifacts/model.joblib ./artifacts/model.joblib
RUN addgroup --system app && adduser --system --ingroup app --home /app app \
    && chown -R app:app /app
USER app
EXPOSE 50051
CMD ["python", "-m", "crypto_signal_engine"]

FROM runtime AS development
