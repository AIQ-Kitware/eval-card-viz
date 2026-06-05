FROM python:3.11

RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

COPY --chown=user . /app
RUN pip install --no-cache-dir uv && \
    uv sync
CMD ["uv", "run", "python", "visualization.py", "./evaluations"]