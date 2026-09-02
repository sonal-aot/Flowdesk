# The backend: the API and the workflow engine. Nothing else.
#
# The console is a separate image (frontend/Dockerfile) whose nginx proxies to
# this one, so this serves no static files and needs no CORS.
#
# Needs vendor/m8flow_bpmn_core-*.whl in the build context. It is gitignored, so
# run ./scripts/refresh_wheel.sh first.

FROM python:3.12-slim

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

# The database lives on a volume; nothing else here has to be writable.
RUN useradd --create-home --uid 10001 flowdesk \
    && mkdir -p /data && chown flowdesk:flowdesk /data
USER flowdesk

ENV PATH="/app/.venv/bin:$PATH" \
    FLOWDESK_DATABASE_URL=sqlite+pysqlite:////data/flowdesk.db \
    FLOWDESK_HOST=0.0.0.0 \
    FLOWDESK_PORT=8020

EXPOSE 8020
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8020/health',timeout=2).status==200 else 1)"

CMD ["flowdesk"]
