FROM python:3.14-slim AS build

ENV PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /workspace

ARG PIP_PROXY=""
COPY contracts ./contracts
COPY src/signal-ml ./src/signal-ml
# Optional pre-fetched wheels. The repo keeps `wheels/` (with a .gitkeep) so this COPY always
# succeeds; drop a heavy wheel (e.g. torch) in there when the proxy cannot sustain one long
# download and the build picks it up via --find-links instead of the network.
COPY wheels ./wheels
# Pre-fetched heavy wheels (torch) when the proxy cannot sustain one long download. The repo keeps
# `wheels/` (with a .gitkeep); drop e.g. the torch wheel there, and this copies it straight into
# /wheels so the main `pip wheel` resolves it locally instead of re-downloading 500MB through the
# proxy. Anything NOT pre-staged is fetched from the index as usual.
# Heavy-wheel staging: when the proxy cannot sustain one long download, put the wheel(s) plus a
# constraints.txt (e.g. `torch==2.13.0+cpu`) in `wheels/`. The constraints pin disqualifies the
# CUDA torch from PyPI in the resolver, so the local CPU wheel is the only candidate. Engine
# inference/training is CPU-only by design, so the CPU build is the correct one regardless.
RUN --mount=type=cache,target=/root/.cache/pip \
    CONSTRAINTS=""; \
    if [ -f ./wheels/constraints.txt ]; then \
        CONSTRAINTS="-c ./wheels/constraints.txt"; \
    fi; \
    if [ -n "$PIP_PROXY" ]; then \
        python -m pip --proxy "$PIP_PROXY" install $CONSTRAINTS "grpcio-tools>=1.81,<1.82"; \
    else \
        python -m pip install $CONSTRAINTS "grpcio-tools>=1.81,<1.82"; \
    fi \
    && python src/signal-ml/scripts/generate_grpc.py \
    && if [ -n "$PIP_PROXY" ]; then \
        python -m pip --proxy "$PIP_PROXY" wheel --wheel-dir /wheels $CONSTRAINTS --find-links ./wheels './src/signal-ml[grpc]'; \
    else \
        python -m pip wheel --wheel-dir /wheels $CONSTRAINTS --find-links ./wheels './src/signal-ml[grpc]'; \
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
        'crypto-ml-signal[grpc]==0.4.0' \
    && rm -rf /wheels
# The model registry, not a single artifact: the engine resolves `<SYMBOL>_<INTERVAL>.joblib` and a
# pooled `_pooled_<INTERVAL>.joblib` per request, so which markets an image can answer for is decided by
# what is in this directory. Copying the directory rather than a named file also means a build with no
# trained bundle produces a container that starts, reports an empty inventory and refuses signals — not
# one that fails to build, and not one that pretends a stale artifact is current.
COPY src/signal-ml/artifacts/models ./artifacts/models
RUN addgroup --system app && adduser --system --ingroup app --home /app app \
    && chown -R app:app /app
USER app
EXPOSE 50051
CMD ["python", "-m", "crypto_signal_engine"]

FROM runtime AS development
