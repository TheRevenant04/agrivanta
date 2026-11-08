FROM node:24-alpine

ENV NODE_ENV=development \
    npm_config_update_notifier=false

WORKDIR /app

COPY package.json package-lock.json .npmrc ./
RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
