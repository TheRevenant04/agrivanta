# syntax=docker/dockerfile:1

# Development image used by docker-compose.yml. Source is bind-mounted by
# Compose, so this image only provides Node.js and the installed dependencies
# required to run the Vite dev server with hot module replacement.
FROM node:24-alpine AS development

ENV NODE_ENV=development \
    npm_config_update_notifier=false

WORKDIR /app

COPY package.json package-lock.json .npmrc ./
RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
