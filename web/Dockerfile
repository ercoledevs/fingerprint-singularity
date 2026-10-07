FROM node:24.11.0-alpine AS build
WORKDIR /build
COPY package.json package-lock.json tsconfig.json ./
COPY src src
RUN npm ci --ignore-scripts && npm run build
COPY web/package.json web/package-lock.json web/
RUN cd web && npm ci --ignore-scripts
COPY web web
COPY client client
COPY scripts/build-sdk.mjs scripts/build-sdk.mjs
RUN cd web && npm run build
RUN node scripts/build-sdk.mjs
FROM nginx:1.28.0-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /build/web/dist /usr/share/nginx/html
