// Lecture centralisée de la configuration (.env). Aucun secret n'est écrit en dur dans le code.
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '..', '.env') });

const fs = require('fs');

const num = (v, def) => (v === undefined || v === '' || isNaN(Number(v)) ? def : Number(v));

// Secret lu dans NOM, ou dans le fichier indiqué par NOM_FILE (secrets Docker : /run/secrets/...)
function secret(name) {
  const file = process.env[`${name}_FILE`];
  if (file) {
    try {
      return fs.readFileSync(file, 'utf8').trim();
    } catch (err) {
      console.error(`[config] impossible de lire ${name}_FILE (${file}) : ${err.code}`);
      return '';
    }
  }
  return process.env[name] || '';
}

// Mot de passe de la base fourni à part (DATABASE_PASSWORD[_FILE]) : on l'insère dans l'URL
function databaseUrl() {
  const url = process.env.DATABASE_URL || '';
  const password = secret('DATABASE_PASSWORD');
  if (!url || !password) return url;
  const u = new URL(url);
  u.password = encodeURIComponent(password);
  return u.toString();
}

const config = {
  port: num(process.env.PORT, 3000),
  groupId: process.env.GROUP_ID || 'g2',
  apiKey: secret('API_KEY'),
  mqtt: {
    url: process.env.MQTT_URL || 'mqtt://localhost:1883',
    username: process.env.MQTT_USERNAME || undefined,
    password: secret('MQTT_PASSWORD') || undefined,
    caFile: process.env.MQTT_CA_FILE || '',
  },
  databaseUrl: databaseUrl(),
  videoUrl: process.env.VIDEO_URL || 'http://localhost:5000/video',
  gasThreshold: num(process.env.GAS_THRESHOLD, 400),
  tempThreshold: num(process.env.TEMP_THRESHOLD, 40),
  offlineAfter: num(process.env.OFFLINE_AFTER, 10),
  dashboardDir: process.env.DASHBOARD_DIR || path.join(__dirname, '..', '..', 'dashboard'),
};

config.topics = {
  telemetry: `sentinel/${config.groupId}/telemetry`,
  status: `sentinel/${config.groupId}/status`,
  cmd: `sentinel/${config.groupId}/cmd`,
};

if (!config.apiKey || config.apiKey === 'change-moi') {
  // Clé par défaut = clé publique (elle est dans le dépôt) : on la désactive, les routes protégées refusent tout.
  config.apiKey = '';
  console.warn('[config] ATTENTION : API_KEY absente ou par défaut. Routes protégées désactivées. Définis-la dans api/.env');
}

module.exports = config;
