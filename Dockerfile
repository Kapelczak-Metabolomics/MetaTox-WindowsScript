FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    APP_ROOT=/app \
    METATOX_PORT=8501 \
    METATOX_VERBOSE=true \
    METATOX_NATIVE_COMPILE=true \
    SINGULARITY_CACHEDIR=/var/lib/metatox/singularity-cache \
    APPTAINER_CACHEDIR=/var/lib/metatox/singularity-cache \
    APPTAINER_BINDPATH=/app \
    APPTAINER_NO_MOUNT=/etc/localtime \
    SINGULARITY_NO_MOUNT=/etc/localtime \
    APPTAINER_TMPDIR=/tmp/apptainer \
    SINGULARITY_TMPDIR=/tmp/apptainer \
    TMPDIR=/tmp \
    MPLBACKEND=Agg

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    dos2unix \
    file \
    fontconfig \
    fuse \
    gawk \
    git \
    libsm6 \
    libxext6 \
    libxrender1 \
    python3 \
    python3-pip \
    squashfuse \
    tzdata \
    uidmap \
    wget \
    && ln -sf /usr/share/zoneinfo/UTC /etc/localtime \
    && rm -rf /var/lib/apt/lists/*

ARG APPTAINER_VERSION=1.3.6
RUN wget -q "https://github.com/apptainer/apptainer/releases/download/v${APPTAINER_VERSION}/apptainer_${APPTAINER_VERSION}_amd64.deb" \
    && apt-get update \
    && apt-get install -y --no-install-recommends ./apptainer_${APPTAINER_VERSION}_amd64.deb \
    && rm -f "apptainer_${APPTAINER_VERSION}_amd64.deb" \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/apptainer /usr/local/bin/singularity

COPY web_app/requirements.txt /tmp/requirements.txt
COPY docker/requirements-companion.txt /tmp/requirements-companion.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt -r /tmp/requirements-companion.txt

COPY . /app

RUN find /app -type f -name "*.sh" -print -exec dos2unix {} + \
    && chmod +x /app/Metatox.sh /app/docker/entrypoint.sh /app/docker/bootstrap.sh /app/web_app/job_worker.py \
    && mkdir -p /app/data/input /app/data/output /app/data/job /app/log /var/lib/metatox/singularity-cache /tmp/apptainer

EXPOSE 8501

VOLUME ["/app/data/input", "/app/data/output", "/var/lib/metatox/singularity-cache"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${METATOX_PORT}/api/health" || exit 1

ENTRYPOINT ["/bin/bash", "/app/docker/entrypoint.sh"]
