// Point d'entrée : HTTP (REST + dashboard) + Socket.io + MQTT.
const http = require('http');
const path = require('path');
const express = require('express');
const helmet = require('helmet');
const rateLimit = require('express-rate-limit');
const { Server } = require('socket.io');

const config = require('./config');
const db = require('./db');
const hub = require('./hub');
const mqttBus = require('./mqtt');
const apiRoutes = require('./routes/api');

const app = express();
app.disable('x-powered-by');

// En-têtes de sécurité. La CSP autorise l'image vidéo venant du script IA (autre port).
app.use(
  helmet({
    contentSecurityPolicy: {
      useDefaults: true,
      directives: {
        'img-src': ["'self'", 'data:', 'http:', 'https:'],
        'connect-src': ["'self'", 'ws:', 'wss:'],
        'upgrade-insecure-requests': null,
      },
    },
    crossOriginEmbedderPolicy: false,
  })
);

app.use(express.json({ limit: '10kb' })); // refuse les corps trop gros (anti-DoS basique)

// Limite de débit : 300 requêtes / minute / IP sur l'API
app.use('/api/', rateLimit({ windowMs: 60_000, limit: 300, standardHeaders: true, legacyHeaders: false }));

app.use('/api/v1', apiRoutes);

// Fichiers du dashboard + Chart.js servi en local (pas besoin d'Internet sur le WiFi de table)
app.use('/vendor/chart.js', express.static(path.join(__dirname, '..', 'node_modules', 'chart.js', 'dist')));
app.use(express.static(config.dashboardDir));

// 404 et erreurs : jamais de trace interne renvoyée au client
app.use('/api/', (req, res) => res.status(404).json({ error: 'route inconnue' }));
app.use((err, req, res, next) => {
  if (err.type === 'entity.parse.failed') return res.status(400).json({ error: 'JSON invalide' });
  if (err.type === 'entity.too.large') return res.status(413).json({ error: 'corps trop volumineux' });
  console.error('[http] erreur :', err.message);
  res.status(500).json({ error: 'erreur interne' });
});

const server = http.createServer(app);
const io = new Server(server, { maxHttpBufferSize: 1e4 });
hub.attachIo(io);

io.on('connection', (socket) => {
  socket.emit('status', hub.publicStatus());
});

async function start() {
  await db.init();
  console.log(`[db] stockage : ${db.kind}`);
  mqttBus.connect();
  server.listen(config.port, '0.0.0.0', () => {
    console.log(`[http] API + dashboard sur http://localhost:${config.port}`);
  });
}

async function shutdown() {
  console.log('Arrêt...');
  io.close();
  await mqttBus.close();
  await db.close();
  process.exit(0);
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

start().catch((err) => {
  console.error('Démarrage impossible :', err.message);
  process.exit(1);
});
