// Connexion au broker Mosquitto : écoute la télémétrie, publie les commandes.
const fs = require('fs');
const mqtt = require('mqtt');
const config = require('./config');
const hub = require('./hub');
const { validateTelemetry } = require('./validate');

let client = null;

function connect() {
  const options = {
    clientId: `sentinel-api-${config.groupId}-${Math.random().toString(16).slice(2, 8)}`,
    username: config.mqtt.username,
    password: config.mqtt.password,
    reconnectPeriod: 2000, // reconnexion automatique toutes les 2 s
    connectTimeout: 5000,
  };
  if (config.mqtt.caFile) {
    options.ca = fs.readFileSync(config.mqtt.caFile);
    options.rejectUnauthorized = true;
  }

  client = mqtt.connect(config.mqtt.url, options);

  client.on('connect', () => {
    console.log(`[mqtt] connecté à ${config.mqtt.url}`);
    client.subscribe([config.topics.telemetry, config.topics.status], { qos: 0 }, (err) => {
      if (err) console.error('[mqtt] abonnement impossible :', err.message);
      else console.log(`[mqtt] abonné à ${config.topics.telemetry} et ${config.topics.status}`);
    });
  });
  client.on('reconnect', () => console.log('[mqtt] reconnexion...'));
  client.on('error', (err) => console.error('[mqtt] erreur :', err.message));

  client.on('message', async (topic, buffer) => {
    try {
      if (buffer.length > 2048) return; // message anormalement gros : ignoré

      if (topic === config.topics.status) {
        const s = buffer.toString().trim();
        if (s === 'online') hub.setOnline(true);
        else if (s === 'offline') hub.setOnline(false);
        return;
      }

      if (topic === config.topics.telemetry) {
        let raw;
        try {
          raw = JSON.parse(buffer.toString());
        } catch {
          console.warn('[mqtt] JSON illisible ignoré');
          return;
        }
        const result = validateTelemetry(raw);
        if (!result.ok) {
          console.warn('[mqtt] télémétrie rejetée :', result.errors.join('; '));
          return;
        }
        await hub.handleTelemetry(result.value);
      }
    } catch (err) {
      console.error('[mqtt] erreur de traitement :', err.message);
    }
  });

  return client;
}

function publishCommand(cmd) {
  return new Promise((resolve, reject) => {
    if (!client || !client.connected) return reject(new Error('broker MQTT non connecté'));
    client.publish(config.topics.cmd, JSON.stringify(cmd), { qos: 1 }, (err) => (err ? reject(err) : resolve()));
  });
}

function isConnected() {
  return Boolean(client && client.connected);
}

function close() {
  return new Promise((resolve) => (client ? client.end(false, {}, resolve) : resolve()));
}

module.exports = { connect, publishCommand, isConnected, close };
