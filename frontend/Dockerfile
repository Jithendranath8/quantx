# ======================================================================
# QuantX Frontend — Multi-stage Dockerfile
# ======================================================================

# ----- Base stage -----
FROM node:20-alpine AS base
WORKDIR /app
# Copy the lockfile too, so `npm ci` has something to install from.
COPY package.json package-lock.json* ./

# ----- Development stage -----
FROM base AS development
RUN npm install
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# ----- Build stage -----
FROM base AS build
# `npm ci` requires a lockfile; fall back to `npm install` when one has not
# been committed yet rather than failing the whole image build.
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY . .
RUN npm run build

# ----- Production stage -----
FROM nginx:alpine AS production
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null 2>&1 || exit 1
CMD ["nginx", "-g", "daemon off;"]
