# The console: a static build, served by nginx, which also proxies the API.
#
# Proxying rather than pointing the browser at the backend directly, so the app
# is one origin: no CORS, and no API base URL baked into the bundle.

FROM node:22-alpine AS build

WORKDIR /build
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . ./
# Empty on purpose: the client falls back to relative URLs, which is what the
# proxy below expects.
ENV VITE_API_BASE=""
RUN npm run build


FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /build/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s \
    CMD wget --spider -q http://127.0.0.1/ || exit 1
