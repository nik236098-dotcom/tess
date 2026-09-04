# Приложению не нужны зависимости — хватает чистого Node.
FROM node:22-alpine

WORKDIR /app
COPY package.json ./
COPY server ./server
COPY public ./public

ENV PORT=3000
EXPOSE 3000

USER node
CMD ["node", "server/index.js"]
