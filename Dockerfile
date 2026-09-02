# One image: the console and the API on one port, which is the whole app.
#
# The frontend is built and served by FastAPI as static files, so there is no
# second server, no CORS and no API base URL to configure -- the browser asks
# the same origin it loaded from.
#
# Needs vendor/m8flow_bpmn_core-*.whl in the build context. It is gitignored, so
# run ./scripts/refresh_wheel.sh first (or docker compose build, which says so).

# ---------------------------------------------------------------- the frontend
FROM node:22-alpine AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
# `npm ci` needs a lockfile; fall back so a fresh checkout still builds.
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY frontend/ ./
# Empty on purpose: the client falls back to relative URLs, which is what
# same-origin serving wants.
ENV VITE_API_BASE=""
RUN npm run build


# ----------------------------------------------------------------- the backend
FROM python:3.12-slim AS backend

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Dependencies first, so editing the app does not reinstall the world.
COPY pyproject.toml uv.lock ./
COPY vendor/ ./vendor/
RUN test -n "$(ls vendor/m8flow_bpmn_core-*.whl 2>/dev/null)" \
    || { echo "ERROR: vendor/m8flow_bpmn_core-*.whl is missing. Run ./scripts/refresh_wheel.sh"; exit 1; }
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
COPY examples/ ./examples/
RUN uv sync --frozen --no-dev

COPY --from=frontend /build/dist /app/static

# The database lives on a volume; the working directory does not have to be
# writable for anything else.
RUN useradd --create-home --uid 10001 flowdesk \
    && mkdir -p /data && chown flowdesk:flowdesk /data
USER flowdesk

ENV PATH="/app/.venv/bin:$PATH" \
    FLOWDESK_STATIC_DIR=/app/static \
    FLOWDESK_DATABASE_URL=sqlite+pysqlite:////data/flowdesk.db \
    FLOWDESK_HOST=0.0.0.0 \
    FLOWDESK_PORT=8020

EXPOSE 8020
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8020/health',timeout=2).status==200 else 1)"

CMD ["flowdesk"]
