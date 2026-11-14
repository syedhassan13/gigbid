# Single-container image for the public deployment (Hugging Face Docker Space, port 7860).
# Runs GigSim + the API (which serves the React build, runs the embedded worker and talks to
# the three MCP servers over the in-process MCP transport). docker compose (infra/) runs the
# same code as separate services.
FROM node:22-alpine AS web
WORKDIR /web
COPY apps/web/package*.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/app GIGBID_HOME=/data HOME=/data \
    GIGSIM_URL=http://127.0.0.1:8100 GIGSIM_DB=/data/gigsim.db GIGSIM_AUTOTICK_SECONDS=60 \
    MCP_TRANSPORT=inproc WEB_DIST=/app/apps/web/dist GIGBID_SCOUT_MAX=4
RUN useradd -m -u 1000 app && mkdir -p /data && chown app /data
WORKDIR /app
COPY pyproject.toml ./
RUN python -c 'import tomllib,subprocess,sys;d=tomllib.load(open("pyproject.toml","rb"))["project"]["dependencies"];subprocess.check_call([sys.executable,"-m","pip","install",*d])'
COPY --chown=app . .
COPY --from=web --chown=app /web/dist /app/apps/web/dist
USER app
RUN GIGBID_HOME=/app python -c "from rag.index.models import embed, rerank; embed(['warm']); rerank('q',['d'])" && \
    mkdir -p /data/var && cp -r /app/var/models /data/var/models 2>/dev/null || true
EXPOSE 7860
CMD ["sh", "scripts/start_space.sh"]
