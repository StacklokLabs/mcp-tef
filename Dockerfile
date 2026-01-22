# SQLite-vec builder stage - separate stage for better caching
FROM python:3.13-slim AS sqlite-vec-builder

# Install build dependencies for compiling sqlite-vec
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    make \
    git \
    gettext \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

# Build sqlite-vec extension with cache mount for git and build artifacts
WORKDIR /tmp
RUN --mount=type=cache,target=/var/cache/git \
    --mount=type=cache,target=/tmp/sqlite-vec-build \
    git clone --depth 1 --branch v0.1.6 https://github.com/asg017/sqlite-vec.git

WORKDIR /tmp/sqlite-vec
RUN --mount=type=cache,target=/tmp/sqlite-vec-build \
    make loadable && \
    mkdir -p /sqlite-vec-dist && \
    cp dist/vec0.* /sqlite-vec-dist/

# Main builder stage
FROM python:3.13-slim AS builder

# Create non-root user
RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid app --shell /bin/bash --create-home app

# Install uv
COPY --from=ghcr.io/astral-sh/uv@sha256:9a23023be68b2ed09750ae636228e903a54a05ea56ed03a934d00fe9fbeded4b /uv /uvx /bin/

# Set working directory and change ownership
WORKDIR /app
RUN chown app:app /app

# Switch to non-root user
USER app

# Copy source code
COPY --chown=app:app src/ ./src/

# Copy mcp-tef-models package
COPY --chown=app:app mcp-tef-models/ ./mcp-tef-models/

# Sync the project
RUN --mount=type=cache,target=/home/app/.cache/uv,uid=1000,gid=1000 \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=README.md,target=README.md \
    uv sync --package mcp-tef --no-dev --locked --no-editable

# Copy pre-built sqlite-vec extension
COPY --from=sqlite-vec-builder /sqlite-vec-dist/vec0.so /app/.venv/lib/python3.13/site-packages/sqlite_vec/vec0.so
USER root
RUN chown app:app /app/.venv/lib/python3.13/site-packages/sqlite_vec/vec0.so
USER app

FROM python:3.13-slim AS runner

# Create non-root user (same as builder stage)
RUN groupadd --gid 1000 app && \
    useradd --uid 1000 --gid app --shell /bin/bash --create-home app

# Create app directory and set ownership
WORKDIR /app
RUN chown app:app /app

# Copy the environment
COPY --from=builder --chown=app:app /app/.venv /app/.venv

# Switch to non-root user
USER app

# Create data directory for SQLite database
RUN mkdir -p /app/data

# Expose application port
EXPOSE 8000

# Set environment variables
ENV DATABASE_URL=sqlite:///./data/mcp_eval.db
ENV LOG_LEVEL=INFO
ENV PORT=8000

# Run the application
CMD ["/app/.venv/bin/tef"]
