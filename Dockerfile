# syntax=docker/dockerfile:1
ARG XRAY_VERSION=26.3.27
FROM ghcr.io/xtls/xray-core:${XRAY_VERSION}@sha256:592ec4d11f656db95598d01e76dbcc6e002d67360b96a5436500a938230f52c7 AS xray
FROM python:3.12-alpine3.22
ARG XRAY_VERSION

ENV XRAY_VERSION=${XRAY_VERSION} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN mkdir -p /etc/xray /data /opt/xray/scripts /opt/xray/config /opt/xray/site

COPY --from=xray /usr/local/bin/xray /usr/local/bin/xray
COPY scripts/ /opt/xray/scripts/
COPY config/reality-sni-candidates.txt /opt/xray/config/reality-sni-candidates.txt
COPY site/ /opt/xray/site/

RUN chmod 0755 /usr/local/bin/xray /opt/xray/scripts/*.sh /opt/xray/scripts/*.py \
    && chmod 0644 /opt/xray/config/reality-sni-candidates.txt /opt/xray/site/*

# Railway networking contract: Gateway is the only application listener that
# is externally targeted. Xray listener ports are allocated at runtime and
# are intentionally NOT exposed or configured as fixed environment values.
ENV PORT=8080 \
    XRAY_LOGLEVEL=warning \
    DATA_DIR=/data \
    XRAY_CONFIG=/etc/xray/config.json \
    REALITY_FINGERPRINT=chrome \
    XHTTP_PATH=/xhttp \
    XHTTP_MODE=auto \
    GRPC_SERVICE_NAME=grpc \
    ENABLE_VLESS_ENCRYPTION=false \
    REALITY_SNI_CANDIDATES_FILE=/opt/xray/config/reality-sni-candidates.txt \
    SUBSCRIPTION_FILE=/data/subscription.txt \
    SUBSCRIPTION_TOKEN_FILE=/data/subscription_token.txt

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
    CMD python3 -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT','8080'), timeout=3).read()"

WORKDIR /opt/xray
ENTRYPOINT ["/opt/xray/scripts/start.sh"]
