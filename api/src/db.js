// Stockage : PostgreSQL si DATABASE_URL est défini, sinon mémoire (pour développer sans Docker).
const config = require('./config');

const MAX_MEMORY = 5000;

function memoryStore() {
  const telemetry = [];
  const alerts = [];
  let nextAlertId = 1;
  return {
    kind: 'memoire',
    async init() {},
    async insertTelemetry(t) {
      telemetry.push(t);
      if (telemetry.length > MAX_MEMORY) telemetry.shift();
      return t;
    },
    async listTelemetry(limit) {
      return telemetry.slice(-limit);
    },
    async insertAlert(a) {
      const row = { id: nextAlertId++, ...a };
      alerts.push(row);
      if (alerts.length > MAX_MEMORY) alerts.shift();
      return row;
    },
    async listAlerts(limit) {
      return alerts.slice(-limit).reverse();
    },
    async close() {},
  };
}

function postgresStore() {
  const { Pool } = require('pg');
  const pool = new Pool({ connectionString: config.databaseUrl, max: 5 });
  pool.on('error', (err) => console.error('[db] erreur PostgreSQL :', err.message));

  return {
    kind: 'postgresql',
    async init() {
      // Plusieurs tentatives : au démarrage de Docker, la base met quelques secondes à être prête.
      for (let i = 1; i <= 10; i++) {
        try {
          await pool.query(`
            CREATE TABLE IF NOT EXISTS telemetry (
              id BIGSERIAL PRIMARY KEY,
              ts TIMESTAMPTZ NOT NULL DEFAULT now(),
              device TEXT NOT NULL,
              temp REAL, hum REAL, gas INTEGER, motion BOOLEAN,
              rssi INTEGER, uptime INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON telemetry (ts DESC);
            CREATE TABLE IF NOT EXISTS alerts (
              id BIGSERIAL PRIMARY KEY,
              ts TIMESTAMPTZ NOT NULL DEFAULT now(),
              source TEXT NOT NULL, type TEXT NOT NULL, level TEXT NOT NULL,
              message TEXT, data JSONB
            );
            CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts (ts DESC);
          `);
          return;
        } catch (err) {
          console.warn(`[db] base pas encore prête (essai ${i}/10) : ${err.message}`);
          await new Promise((r) => setTimeout(r, 3000));
        }
      }
      throw new Error('Impossible de se connecter à PostgreSQL');
    },
    async insertTelemetry(t) {
      await pool.query(
        `INSERT INTO telemetry (ts, device, temp, hum, gas, motion, rssi, uptime)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8)`,
        [t.ts, t.device, t.temp, t.hum, t.gas, t.motion, t.rssi, t.uptime]
      );
      return t;
    },
    async listTelemetry(limit) {
      const { rows } = await pool.query(
        `SELECT ts, device, temp, hum, gas, motion, rssi, uptime
         FROM telemetry ORDER BY ts DESC LIMIT $1`,
        [limit]
      );
      return rows.reverse();
    },
    async insertAlert(a) {
      const { rows } = await pool.query(
        `INSERT INTO alerts (ts, source, type, level, message, data)
         VALUES ($1,$2,$3,$4,$5,$6) RETURNING id, ts, source, type, level, message, data`,
        [a.ts, a.source, a.type, a.level, a.message, a.data]
      );
      return rows[0];
    },
    async listAlerts(limit) {
      const { rows } = await pool.query(
        `SELECT id, ts, source, type, level, message, data
         FROM alerts ORDER BY ts DESC LIMIT $1`,
        [limit]
      );
      return rows;
    },
    async close() {
      await pool.end();
    },
  };
}

module.exports = config.databaseUrl ? postgresStore() : memoryStore();
