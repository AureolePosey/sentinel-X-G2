// Le "cerveau" de l'API : reçoit les mesures et alertes, les enregistre,
// détecte les changements d'état et les diffuse en direct au dashboard.
const config = require('./config');
const db = require('./db');

let io = null; // instance Socket.io, branchée par server.js

const state = {
  online: false,
  lastSeen: null,
  last: null, // dernière mesure
  active: { gas: false, motion: false, temp: false }, // alertes physiques en cours
};

function attachIo(ioInstance) {
  io = ioInstance;
}

function emit(event, payload) {
  if (io) io.emit(event, payload);
}

async function addAlert(alert) {
  const row = await db.insertAlert({ ts: new Date(), ...alert });
  console.log(`[alerte] ${row.level.toUpperCase()} ${row.type} (${row.source}) ${row.message || ''}`);
  emit('alert', row);
  return row;
}

function setOnline(online) {
  if (state.online === online) return;
  state.online = online;
  emit('status', publicStatus());
  addAlert({
    source: 'api',
    type: online ? 'device_online' : 'device_offline',
    level: online ? 'info' : 'warning',
    message: online ? 'Boîtier Sentinel-X connecté' : 'Boîtier Sentinel-X injoignable',
    data: null,
  }).catch((e) => console.error('[hub]', e.message));
}

// Alerte uniquement sur un CHANGEMENT d'état (front montant), pas à chaque mesure.
async function checkTransition(key, isActive, alertIfOn) {
  if (isActive && !state.active[key]) {
    state.active[key] = true;
    await addAlert(alertIfOn);
  } else if (!isActive && state.active[key]) {
    state.active[key] = false;
    await addAlert({
      source: 'api', type: 'state_change', level: 'info',
      message: `Retour à la normale : ${key}`, data: { sensor: key },
    });
  }
}

async function handleTelemetry(t) {
  const row = { ts: new Date(), ...t };
  state.last = row;
  state.lastSeen = row.ts;
  setOnline(true);

  await db.insertTelemetry(row);
  emit('telemetry', row);

  await checkTransition('gas', t.gas >= config.gasThreshold, {
    source: 'esp8266', type: 'gas_detected', level: 'critical',
    message: `Gaz détecté : ${t.gas} (seuil ${config.gasThreshold})`, data: { gas: t.gas },
  });
  await checkTransition('motion', t.motion === true, {
    source: 'esp8266', type: 'motion_detected', level: 'warning',
    message: 'Mouvement détecté par le capteur PIR', data: null,
  });
  if (t.temp !== null) {
    await checkTransition('temp', t.temp >= config.tempThreshold, {
      source: 'esp8266', type: 'temp_high', level: 'critical',
      message: `Surchauffe : ${t.temp} °C (seuil ${config.tempThreshold})`, data: { temp: t.temp },
    });
  }
}

function publicStatus() {
  return {
    online: state.online,
    lastSeen: state.lastSeen,
    last: state.last,
    active: { ...state.active },
  };
}

// Chien de garde : pas de message depuis OFFLINE_AFTER secondes => hors ligne.
setInterval(() => {
  if (state.online && state.lastSeen && Date.now() - state.lastSeen.getTime() > config.offlineAfter * 1000) {
    setOnline(false);
  }
}, 2000).unref();

module.exports = { attachIo, handleTelemetry, addAlert, setOnline, publicStatus };
