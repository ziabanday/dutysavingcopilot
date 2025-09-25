FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install build helpers first
RUN python -m pip install --upgrade pip setuptools wheel

# Copy only requirements first (cache-friendly)
COPY requirements.txt /app/requirements.txt

# If you are behind a proxy, you can pass these at build time:
#   docker build --build-arg HTTPS_PROXY=%HTTPS_PROXY% --build-arg HTTP_PROXY=%HTTP_PROXY% ...
ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV http_proxy=${HTTP_PROXY}
ENV https_proxy=${HTTPS_PROXY}

# Install deps (with timeout and no cache)
RUN pip install --no-cache-dir --default-timeout=120 -r /app/requirements.txt

# Now copy the app
COPY . /app

EXPOSE 8000

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
