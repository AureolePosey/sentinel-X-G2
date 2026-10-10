// Validation stricte de tout ce qui arrive de l'extérieur (MQTT, HTTP).
// Objectif pentest : un message bizarre est rejeté proprement, il ne fait jamais planter le serveur.

const ALERT_SOURCES = ['esp8266', 'ia-vision', 'ia-anomaly', 'api', 'dashboard'];
const ALERT_TYPES = [
  'gas_detected', 'motion_detected', 'temp_high', 'human_detected',
  'anomaly', 'device_offline', 'device_online', 'state_change',
];
const ALERT_LEVELS = ['info', 'warning', 'critical'];

const COMMANDS = {
  buzzer: ['on', 'off', 'beep'],
  led_red: ['on', 'off'],
  led_green: ['on', 'off'],
  all: ['off'],
};

const isObj = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);
// Caractères de contrôle invisibles (dont \u0000, refusé par PostgreSQL) : on garde seulement \t et \n
const CONTROL_CHARS = /[\u0000-\u0008\u000B-\u001F\u007F]/;
const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
const inRange = (v, min, max) => isNum(v) && v >= min && v <= max;

// Renvoie { ok, value, errors }
function validateTelemetry(raw) {
  const errors = [];
  if (!isObj(raw)) return { ok: false, errors: ['le message doit être un objet JSON'] };

  const device = typeof raw.device === 'string' ? raw.device.slice(0, 40) : '';
  if (!/^[\w.-]{1,40}$/.test(device)) errors.push('device invalide');

  const temp = raw.temp === null || raw.temp === undefined ? null : raw.temp;
  if (temp !== null && !inRange(temp, -40, 125)) errors.push('temp hors plage (-40..125)');

  const hum = raw.hum === null || raw.hum === undefined ? null : raw.hum;
  if (hum !== null && !inRange(hum, 0, 100)) errors.push('hum hors plage (0..100)');

  if (!Number.isInteger(raw.gas) || !inRange(raw.gas, 0, 1023)) errors.push('gas doit être un entier 0..1023');
  if (typeof raw.motion !== 'boolean') errors.push('motion doit être un booléen');

  const rssi = Number.isInteger(raw.rssi) && inRange(raw.rssi, -120, 0) ? raw.rssi : null;
  const uptime = Number.isInteger(raw.uptime) && raw.uptime >= 0 ? raw.uptime : null;

  if (errors.length) return { ok: false, errors };
  return {
    ok: true,
    value: { device, temp, hum, gas: raw.gas, motion: raw.motion, rssi, uptime },
  };
}

function validateAlert(raw) {
  const errors = [];
  if (!isObj(raw)) return { ok: false, errors: ['le corps doit être un objet JSON'] };

  if (!ALERT_SOURCES.includes(raw.source)) errors.push(`source doit valoir : ${ALERT_SOURCES.join(', ')}`);
  if (!ALERT_TYPES.includes(raw.type)) errors.push(`type doit valoir : ${ALERT_TYPES.join(', ')}`);
  if (!ALERT_LEVELS.includes(raw.level)) errors.push(`level doit valoir : ${ALERT_LEVELS.join(', ')}`);

  let message = null;
  if (raw.message !== undefined && raw.message !== null) {
    if (typeof raw.message !== 'string') errors.push('message doit être du texte');
    else if (raw.message.length > 300) errors.push('message trop long (300 max)');
    else if (CONTROL_CHARS.test(raw.message)) errors.push('message contient des caractères de contrôle');
    else message = raw.message;
  }

  let data = null;
  if (raw.data !== undefined && raw.data !== null) {
    if (!isObj(raw.data)) errors.push('data doit être un objet');
    else {
      const json = JSON.stringify(raw.data);
      if (json.length > 2000) errors.push('data trop volumineux (2 Ko max)');
      else if (json.includes('\\u0000')) errors.push('data contient des caractères nuls');
      else data = raw.data;
    }
  }

  if (errors.length) return { ok: false, errors };
  return { ok: true, value: { source: raw.source, type: raw.type, level: raw.level, message, data } };
}

function validateCommand(raw) {
  if (!isObj(raw)) return { ok: false, errors: ['le corps doit être un objet JSON'] };
  const actions = COMMANDS[raw.target];
  if (!actions) return { ok: false, errors: [`target doit valoir : ${Object.keys(COMMANDS).join(', ')}`] };
  if (!actions.includes(raw.action)) {
    return { ok: false, errors: [`action pour ${raw.target} doit valoir : ${actions.join(', ')}`] };
  }
  return { ok: true, value: { target: raw.target, action: raw.action } };
}

module.exports = { validateTelemetry, validateAlert, validateCommand, COMMANDS };
