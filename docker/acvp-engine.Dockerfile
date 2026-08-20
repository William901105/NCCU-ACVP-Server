# syntax=docker/dockerfile:1.7

ARG DOTNET_CHANNEL=8.0

FROM mcr.microsoft.com/dotnet/sdk:${DOTNET_CHANNEL}-bookworm-slim AS nist-build

WORKDIR /src
COPY scripts/nist/ ./scripts/nist/
COPY third_party/nist-acvp-server/ ./third_party/nist-acvp-server/
RUN bash ./scripts/nist/build_nist_genval.sh

FROM python:3.11-slim-bookworm AS python-wheels

WORKDIR /build
COPY backend/requirements.runtime.txt ./requirements.runtime.txt
RUN python -m pip wheel \
    --disable-pip-version-check \
    --no-cache-dir \
    --wheel-dir /wheels \
    --requirement requirements.runtime.txt

FROM mcr.microsoft.com/dotnet/aspnet:${DOTNET_CHANNEL}-bookworm-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:${PATH} \
    DOTNET_CLI_HOME=/tmp/dotnet \
    DOTNET_ENVIRONMENT=Production \
    ACVP_GENVAL_RUNNER_DLL=/opt/acvp/nist/genval-runner/NIST.CVP.ACVTS.Generation.GenValApp.dll \
    ACVP_GENVAL_ARTIFACT_ROOT=/var/lib/acvp/artifacts \
    ACVP_GENVAL_TIMEOUT_SECONDS=300 \
    ACVP_ACCESS_TOKEN_TTL_SECONDS=1800

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        bash \
        ca-certificates \
        python3 \
        python3-venv \
        tar \
        tini \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv "${VIRTUAL_ENV}"

COPY --from=python-wheels /wheels/ /wheels/
COPY backend/requirements.runtime.txt /tmp/requirements.runtime.txt
RUN "${VIRTUAL_ENV}/bin/python" -m pip install \
        --disable-pip-version-check \
        --no-cache-dir \
        --no-index \
        --find-links=/wheels \
        --requirement /tmp/requirements.runtime.txt \
    && rm -rf /wheels /tmp/requirements.runtime.txt

RUN groupadd --gid 10001 acvp \
    && useradd --uid 10001 --gid acvp --no-create-home --shell /usr/sbin/nologin acvp \
    && mkdir -p \
        /opt/acvp/backend \
        /opt/acvp/bin \
        /opt/acvp/nist/genval-runner \
        /opt/acvp/nist/orleans-server \
        /var/lib/acvp/artifacts \
    && chown -R acvp:acvp /opt/acvp /var/lib/acvp

COPY --chown=acvp:acvp backend/app/ /opt/acvp/backend/app/
COPY --from=nist-build --chown=acvp:acvp /src/.nist-bin/genval-runner/ /opt/acvp/nist/genval-runner/
COPY --from=nist-build --chown=acvp:acvp /src/.nist-bin/orleans-server/ /opt/acvp/nist/orleans-server/
COPY --chown=acvp:acvp docker/engine-entrypoint.sh docker/engine-healthcheck.py /opt/acvp/bin/

RUN chmod 0555 /opt/acvp/bin/engine-entrypoint.sh /opt/acvp/bin/engine-healthcheck.py \
    && test -f "${ACVP_GENVAL_RUNNER_DLL}" \
    && test -f /opt/acvp/nist/genval-runner/sharedappsettings.json \
    && test -f /opt/acvp/nist/orleans-server/NIST.CVP.ACVTS.Orleans.ServerHost.dll \
    && test -f /opt/acvp/nist/orleans-server/sharedappsettings.json

ARG APP_VERSION=dev
ARG VCS_REF=unknown
ARG BUILD_DATE=unknown
ARG NIST_SOURCE_COMMIT=a7f283cdc87d2d6dd93c1bac59e5622c5f9f8324

LABEL org.opencontainers.image.title="NCCU ACVP Engine" \
      org.opencontainers.image.description="FastAPI, NIST GenVal Runner, and Orleans runtime for FIPS 203/204 ACVP" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="NCCU ACVP Server" \
      org.opencontainers.image.nist-source-commit="${NIST_SOURCE_COMMIT}"

USER acvp
WORKDIR /opt/acvp/backend

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=8s --start-period=90s --retries=5 \
    CMD ["python", "/opt/acvp/bin/engine-healthcheck.py"]

ENTRYPOINT ["/usr/bin/tini", "--", "/opt/acvp/bin/engine-entrypoint.sh"]
