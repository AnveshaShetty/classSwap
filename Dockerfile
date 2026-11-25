ARG PYTHON_IMAGE=python:3.14-alpine@sha256:5862d971d1f0ae26b258cefa4e893556b1d3aba81bd2ff30888704ad378bab67

FROM ${PYTHON_IMAGE} AS dependencies
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY requirements.txt .
RUN python -m pip install --require-hashes --prefix=/install -r requirements.txt

FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN addgroup -S -g 10001 app \
    && adduser -S -u 10001 -G app -h /app -H app
WORKDIR /app
COPY --from=dependencies /install/ /usr/local/
COPY --chown=10001:10001 . /app
RUN python -m pip uninstall -y pip
USER 10001:10001

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health', timeout=2)"]
CMD ["sh", "-c", "if [ \"${ENV:-development}\" != \"production\" ]; then alembic upgrade head || exit $?; fi; exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-server-header --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS:-127.0.0.1}\""]
