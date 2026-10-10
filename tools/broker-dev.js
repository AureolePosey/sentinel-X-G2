// Mini broker MQTT pour DÉVELOPPER sans Docker ni Mosquitto (port 1883, sans TLS, sans mot de passe).
// À ne PAS utiliser en démo : en démo, c'est le Mosquitto de l'équipe cloud (avec TLS).
// Lancement (depuis le dossier api/) : npm run broker
const path = require('path');
const net = require('net');
const apiDir = path.join(__dirname, '..', 'api');
const aedes = require(require.resolve('aedes', { paths: [apiDir] }))();

const PORT = 1883;
const server = net.createServer(aedes.handle);

server.listen(PORT, () => console.log(`[broker-dev] broker MQTT de test sur mqtt://localhost:${PORT}`));
aedes.on('client', (c) => console.log(`[broker-dev] client connecté : ${c.id}`));
aedes.on('clientDisconnect', (c) => console.log(`[broker-dev] client parti : ${c.id}`));
