FROM python:3.11-slim AS builder

RUN pip install --no-cache-dir uv==0.13.6

ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
RUN uv sync --locked --no-dev --no-editable

FROM python:3.11-slim AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY tests/fixtures/synthetic-scenarios.json examples/synthetic-scenarios.json

USER 10001:10001

ENTRYPOINT ["cs-map-trainer"]
CMD ["--help"]
