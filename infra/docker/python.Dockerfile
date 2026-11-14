# One image for every Python service (api, worker, gigsim, mcp servers); the compose `command` picks the role.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/app GIGBID_HOME=/data
WORKDIR /app
COPY pyproject.toml README.md ./
RUN python -c 'import tomllib,subprocess,sys;d=tomllib.load(open("pyproject.toml","rb"))["project"]["dependencies"];subprocess.check_call([sys.executable,"-m","pip","install",*d])'
COPY . .
RUN python -c "from rag.index.models import embed, rerank; embed(['warm']); rerank('q',['d'])" || true
RUN mkdir -p /data
EXPOSE 8000 8100 8201 8202 8203
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
