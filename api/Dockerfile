# Image de l'API Sentinel-X. À construire depuis la RACINE du dépôt :
#   docker build -f api/Dockerfile -t sentinel-api .
FROM node:20-alpine

WORKDIR /app/api
ENV NODE_ENV=production

COPY api/package*.json ./
RUN npm install --omit=dev && npm cache clean --force

COPY api/src ./src
COPY dashboard /app/dashboard

# Ne pas tourner en root dans le conteneur (exigence hardening)
USER node

EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3000/api/v1/health || exit 1

CMD ["node", "src/server.js"]
