// Routes REST /api/v1
const crypto = require('crypto');
const express = require('express');
const rateLimit = require('express-rate-limit');
const config = require('../config');
const db = require('../db');
const hub = require('../hub');
const mqttBus = require('../mqtt');
const { validateAlert, validateCommand } = require('../validate');

const router = express.Router();

// Comparaison en temps constant pour éviter de deviner la clé caractère par caractère.
function requireApiKey(req, res, next) {
  const given = Buffer.from(String(req.get('X-API-Key') || ''));
  const expected = Buffer.from(config.apiKey);
  if (!config.apiKey || given.length !== expected.length || !crypto.timingSafeEqual(given, expected)) {
    // Journal des tentatives refusées (jamais la clé essayée elle-même)
    console.warn(`[securite] clé API refusée : ${req.method} ${req.originalUrl} depuis ${req.ip}`);
    return res.status(401).json({ error: 'clé API absente ou invalide' });
  }
  next();
}

// Anti force brute : 20 clés fausses en 5 minutes => l'IP est bloquée jusqu'à la fin de la fenêtre.
// Seuls les refus 401 comptent : une erreur de format (400) de l'IA ne la bloque pas.
const authFailLimiter = rateLimit({
  windowMs: 5 * 60_000,
  limit: 20,
  standardHeaders: true,
  legacyHeaders: false,
  requestWasSuccessful: (req, res) => res.statusCode !== 401,
  skipSuccessfulRequests: true,
  handler: (req, res) => {
    console.warn(`[securite] trop de clés refusées, IP bloquée 5 min : ${req.ip}`);
    res.status(429).json({ error: 'trop de tentatives, réessaie plus tard' });
  },
});

const limitParam = (v, def, max) => {
  const n = parseInt(v, 10);
  return Number.isInteger(n) && n > 0 ? Math.min(n, max) : def;
};

router.get('/health', (req, res) => {
  res.json({ ok: true, mqtt: mqttBus.isConnected(), storage: db.kind, time: new Date() });
});

router.get('/status', (req, res) => {
  res.json({ ...hub.publicStatus(), mqtt: mqttBus.isConnected() });
});

router.get('/config', (req, res) => {
  res.json({
    groupId: config.groupId,
    videoUrl: config.videoUrl,
    gasThreshold: config.gasThreshold,
    tempThreshold: config.tempThreshold,
  });
});

router.get('/telemetry', async (req, res, next) => {
  try {
    res.json(await db.listTelemetry(limitParam(req.query.limit, 100, 1000)));
  } catch (e) { next(e); }
});

router.get('/alerts', async (req, res, next) => {
  try {
    res.json(await db.listAlerts(limitParam(req.query.limit, 50, 500)));
  } catch (e) { next(e); }
});

// Route OBLIGATOIRE du sujet
router.post('/alerts', authFailLimiter, requireApiKey, async (req, res, next) => {
  try {
    const result = validateAlert(req.body);
    if (!result.ok) return res.status(400).json({ errors: result.errors });
    const row = await hub.addAlert(result.value);
    res.status(201).json(row);
  } catch (e) { next(e); }
});

router.post('/commands', authFailLimiter, requireApiKey, async (req, res, next) => {
  try {
    const result = validateCommand(req.body);
    if (!result.ok) return res.status(400).json({ errors: result.errors });
    await mqttBus.publishCommand(result.value);
    await hub.addAlert({
      source: 'dashboard', type: 'state_change', level: 'info',
      message: `Commande envoyée : ${result.value.target} -> ${result.value.action}`, data: result.value,
    });
    res.status(202).json({ sent: result.value });
  } catch (e) {
    if (e.message.includes('MQTT')) return res.status(503).json({ error: e.message });
    next(e);
  }
});

module.exports = router;
