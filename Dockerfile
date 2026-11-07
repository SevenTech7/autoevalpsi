# Entorno de desarrollo y tests. Todo corre aquí; nada se instala en el equipo anfitrión.
FROM python:3.12-slim

RUN pip install --no-cache-dir uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_CACHE_DIR=/opt/uv-cache \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY pyproject.toml uv.lock* ./
COPY src ./src
RUN uv sync --all-extras

CMD ["pytest"]
