# SKYVAULT (Phase 21: one command, `skyvault`; the UI from the same service).
# docker compose up starts the service, a worker, Redis and PostgreSQL.

# The UI: a static Next.js build the service serves at /
FROM node:22-slim AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /skyvault
COPY pyproject.toml README.md ./
COPY src ./src
COPY data ./data
COPY --from=ui /ui/out ./ui/out
# editable: SKYVAULT reads its own data/ next to src/
RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["skyvault", "serve", "--host", "0.0.0.0"]
