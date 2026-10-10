// Simulateur de boîtier ESP8266 : publie de fausses mesures comme le vrai firmware.
// Permet de développer l'API et le dashboard SANS le matériel.
// Lancement (depuis le dossier api/) : npm run simulate
const path = require('path');
const apiDir = path.join(__dirname, '..', 'api');
require(require.resolve('dotenv', { paths: [apiDir] })).config({ path: path.join(apiDir, '.env') });
const mqtt = require(require.resolve('mqtt', { paths: [apiDir] }));

const GROUP = process.env.GROUP_ID || 'g2';
const URL = process.env.MQTT_URL || 'mqtt://localhost:1883';
const T = {
  telemetry: `sentinel/${GROUP}/telemetry`,
  status: `sentinel/${GROUP}/status`,
  cmd: `sentinel/${GROUP}/cmd`,
};

const client = mqtt.connect(URL, {
  clientId: `simulateur-${GROUP}`,
  username: process.env.MQTT_USERNAME || undefined,
  password: process.env.MQTT_PASSWORD || undefined,
  will: { topic: T.status, payload: 'offline', retain: true, qos: 1 }, // comme le vrai ESP8266
  reconnectPeriod: 2000,
});

let temp = 23, hum = 48, gas = 180, tick = 0;
const start = Date.now();
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

client.on('connect', () => {
  console.log(`[simu] connecté à ${URL}, publication sur ${T.telemetry}`);
  client.publish(T.status, 'online', { retain: true, qos: 1 });
  client.subscribe(T.cmd);
});
client.on('error', (e) => console.error('[simu] erreur :', e.message));

client.on('message', (topic, buf) => {
  console.log(`[simu] COMMANDE REÇUE -> ${buf.toString()}  (le vrai boîtier ferait sonner/allumer)`);
});

setInterval(() => {
  if (!client.connected) return;
  tick++;
  // Marche aléatoire réaliste
  temp = clamp(temp + (Math.random() - 0.5) * 0.3, 15, 60);
  hum = clamp(hum + (Math.random() - 0.5) * 0.8, 20, 90);
  // Toutes les ~60 s : fuite de gaz pendant ~10 s
  const leak = tick % 30 >= 25;
  gas = Math.round(clamp(leak ? gas + 90 : gas - 40 + Math.random() * 30, 120, 900));
  if (!leak) gas = Math.max(gas, 150);
  // Mouvement de temps en temps
  const motion = tick % 20 >= 17;

  const msg = {
    device: `sentinel-${GROUP}`,
    temp: Number(temp.toFixed(1)),
    hum: Number(hum.toFixed(1)),
    gas,
    motion,
    rssi: -50 - Math.round(Math.random() * 15),
    uptime: Math.round((Date.now() - start) / 1000),
  };
  client.publish(T.telemetry, JSON.stringify(msg));
  console.log('[simu]', JSON.stringify(msg));
}, 2000);

process.on('SIGINT', () => {
  client.publish(T.status, 'offline', { retain: true }, () => process.exit(0));
});
