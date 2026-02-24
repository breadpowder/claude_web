# Stage 1: Build frontend
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Python backend + serve frontend
FROM python:3.12-slim AS runtime

# Install curl + Node.js (required by claude-code-sdk for bedrock provider)
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY --from=frontend-build /usr/local/bin/node /usr/local/bin/node
COPY --from=frontend-build /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && \
    npm install -g @anthropic-ai/claude-code

RUN pip install --no-cache-dir uv

# Create non-root user (claude-code-sdk rejects --dangerously-skip-permissions as root)
RUN groupadd -r claude && useradd -r -g claude -m -s /bin/bash claude

WORKDIR /app
COPY pyproject.toml README.md ./
RUN uv sync --no-dev
COPY src/ ./src/
COPY config.yaml ./
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Ensure the non-root user owns the app directory
RUN chown -R claude:claude /app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8000/api/v1/health/live || exit 1

USER claude
CMD ["uv", "run", "uvicorn", "src.main:get_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
