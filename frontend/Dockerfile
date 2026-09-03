# --- Builder ---
FROM node:22-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
RUN npm run build

# --- Runner ---
FROM nginx:1.29-alpine AS runner

# Makes the entrypoint export NGINX_LOCAL_RESOLVERS for the template below.
ENV NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1 \
    BACKEND_URL=http://backend:8000

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:3000/healthz || exit 1
