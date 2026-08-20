# syntax=docker/dockerfile:1.7

FROM node:24-bookworm-slim AS build

ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY index.html tsconfig.json tsconfig.node.json vite.config.ts ./
COPY src/ ./src/
RUN npm run build

FROM nginx:1.28-alpine AS runtime

COPY --from=build /src/dist/ /usr/share/nginx/html/
COPY nginx.conf /etc/nginx/nginx.conf

RUN chown -R nginx:nginx /usr/share/nginx/html \
    && test -f /usr/share/nginx/html/index.html

ARG APP_VERSION=dev
ARG VCS_REF=unknown
ARG BUILD_DATE=unknown

LABEL org.opencontainers.image.title="NCCU ACVP Frontend" \
      org.opencontainers.image.description="Nginx-hosted React client for the NCCU ACVP Server" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.source="NCCU ACVP Server"

USER nginx
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1

ENTRYPOINT ["nginx", "-g", "daemon off;"]
