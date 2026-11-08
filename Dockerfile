# The SKYVAULT world service (development plan Phase 11).
# docker compose up starts the API, a worker, Redis and PostgreSQL.
FROM python:3.11-slim

WORKDIR /skyvault
COPY pyproject.toml README.md ./
COPY src ./src
COPY data ./data
COPY scripts ./scripts
RUN pip install --no-cache-dir .

EXPOSE 8100
CMD ["python", "scripts/serve_world.py", "--host", "0.0.0.0"]
