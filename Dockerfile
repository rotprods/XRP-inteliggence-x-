FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY config ./config
COPY schemas ./schemas
COPY scripts ./scripts
EXPOSE 8080
CMD ["uvicorn", "xrp_regime_engine.api:app", "--host", "0.0.0.0", "--port", "8080"]
