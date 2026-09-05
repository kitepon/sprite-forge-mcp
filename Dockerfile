FROM python:3.13-slim

RUN apt-get update \
    && apt-get install --no-install-recommends -y openssh-client fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /app
ENV SPRITEFORGE_SHEET_FONT=/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend ./backend
COPY web ./web
COPY docker-entrypoint.sh /usr/local/bin/sprite-forge-entrypoint
RUN chmod 755 /usr/local/bin/sprite-forge-entrypoint

ENTRYPOINT ["/usr/local/bin/sprite-forge-entrypoint"]
CMD ["/app/.venv/bin/uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8765"]
