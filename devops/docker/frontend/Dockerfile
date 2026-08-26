FROM node:24-alpine AS development
# tzdata: the compose file sets TZ=Asia/Tehran; without this package the zone is unknown and
# every container falls back to UTC, so vite logs and error timestamps disagree with the API.
RUN apk add --no-cache tzdata
WORKDIR /app
COPY src/frontend/package.json src/frontend/package-lock.json ./
RUN npm ci
COPY src/frontend/. ./
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

FROM development AS build
RUN npm run build

FROM nginx:1.28-alpine AS runtime
RUN apk add --no-cache tzdata
ENV TZ=Asia/Tehran
COPY devops/docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
USER nginx
EXPOSE 8080
