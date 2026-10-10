// Dashboard Sentinel-X : JS natif + Chart.js + Socket.io
(() => {
  const MAX_POINTS = 120; // ~4 minutes à une mesure toutes les 2 s
  const $ = (id) => document.getElementById(id);
  let cfg = { gasThreshold: 400, tempThreshold: 40 };

  // ---------- Graphiques ----------
  Chart.defaults.color = '#8b98a8';
  Chart.defaults.borderColor = '#2b3440';
  Chart.defaults.animation = false;

  const timeLabel = (ts) => new Date(ts).toLocaleTimeString('fr-FR');

  const envChart = new Chart($('chart-env'), {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: 'Température (°C)', data: [], borderColor: '#f97316', tension: 0.3, pointRadius: 0, yAxisID: 'y' },
        { label: 'Humidité (%)', data: [], borderColor: '#38bdf8', tension: 0.3, pointRadius: 0, yAxisID: 'y1' },
      ],
    },
    options: {
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: { ticks: { maxTicksLimit: 6 } },
        y: { position: 'left', title: { display: true, text: '°C' } },
        y1: { position: 'right', min: 0, max: 100, grid: { drawOnChartArea: false }, title: { display: true, text: '%' } },
      },
    },
  });

  const gasChart = new Chart($('chart-gas'), {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: 'Gaz', data: [], borderColor: '#a78bfa', backgroundColor: 'rgba(167,139,250,0.15)', fill: true, tension: 0.3, pointRadius: 0 },
        { label: 'Seuil', data: [], borderColor: '#ef4444', borderDash: [6, 6], pointRadius: 0 },
      ],
    },
    options: {
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: { x: { ticks: { maxTicksLimit: 6 } }, y: { min: 0, max: 1023 } },
    },
  });

  function pushPoint(t, redraw = true) {
    const label = timeLabel(t.ts);
    envChart.data.labels.push(label);
    envChart.data.datasets[0].data.push(t.temp);
    envChart.data.datasets[1].data.push(t.hum);
    gasChart.data.labels.push(label);
    gasChart.data.datasets[0].data.push(t.gas);
    gasChart.data.datasets[1].data.push(cfg.gasThreshold);
    for (const c of [envChart, gasChart]) {
      if (c.data.labels.length > MAX_POINTS) {
        c.data.labels.shift();
        c.data.datasets.forEach((d) => d.data.shift());
      }
    }
    if (redraw) { envChart.update(); gasChart.update(); }
  }

  // ---------- Tuiles ----------
  function showKpis(t) {
    $('v-temp').textContent = t.temp === null ? '--' : t.temp.toFixed(1);
    $('v-hum').textContent = t.hum === null ? '--' : t.hum.toFixed(0);
    $('v-gas').textContent = t.gas;
    $('v-motion').textContent = t.motion ? 'OUI' : 'non';
    $('v-lastseen').textContent = `maj ${timeLabel(t.ts)}`;
    $('kpi-temp').classList.toggle('alarm', t.temp !== null && t.temp >= cfg.tempThreshold);
    $('kpi-gas').classList.toggle('alarm', t.gas >= cfg.gasThreshold);
    $('kpi-motion').classList.toggle('alarm', t.motion);
  }

  function setPill(el, on, textOn, textOff) {
    el.classList.toggle('pill-on', on);
    el.classList.toggle('pill-off', !on);
    el.textContent = on ? textOn : textOff;
  }

  // ---------- Alertes ----------
  const LEVEL_TXT = { info: 'INFO', warning: 'ATTENTION', critical: 'CRITIQUE' };

  function alertItem(a, isNew) {
    const li = document.createElement('li');
    if (isNew) li.classList.add('new');
    const time = document.createElement('span');
    time.className = 'time';
    time.textContent = timeLabel(a.ts);
    const badge = document.createElement('span');
    badge.className = `badge ${a.level}`;
    badge.textContent = LEVEL_TXT[a.level] || a.level;
    const msg = document.createElement('span');
    msg.textContent = a.message || a.type; // textContent : aucune injection HTML possible (XSS)
    const src = document.createElement('span');
    src.className = 'src';
    src.textContent = a.source;
    li.append(time, badge, msg, src);
    return li;
  }

  function addAlert(a, isNew = true) {
    const list = $('alerts');
    list.prepend(alertItem(a, isNew));
    while (list.children.length > 100) list.lastChild.remove();
  }

  // ---------- Vidéo ----------
  function startVideo(url) {
    const img = $('video');
    const off = $('video-off');
    img.onload = () => { off.hidden = true; img.style.visibility = 'visible'; };
    img.onerror = () => {
      off.hidden = false;
      img.style.visibility = 'hidden';
      setTimeout(() => { img.src = `${url}${url.includes('?') ? '&' : '?'}t=${Date.now()}`; }, 5000);
    };
    img.src = url;
  }

  // ---------- Commandes ----------
  const keyInput = $('api-key');
  try { keyInput.value = sessionStorage.getItem('sx-key') || ''; } catch { /* stockage indisponible */ }
  keyInput.addEventListener('change', () => {
    try { sessionStorage.setItem('sx-key', keyInput.value); } catch { /* ignore */ }
  });

  function feedback(text, kind) {
    const el = $('cmd-feedback');
    el.textContent = text;
    el.className = `feedback ${kind || ''}`;
  }

  document.querySelectorAll('.buttons .btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      if (!keyInput.value) { feedback('Saisis la clé opérateur avant d\'envoyer une commande.', 'error'); keyInput.focus(); return; }
      btn.disabled = true;
      try {
        const res = await fetch('/api/v1/commands', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-API-Key': keyInput.value },
          body: JSON.stringify({ target: btn.dataset.target, action: btn.dataset.action }),
        });
        const body = await res.json().catch(() => ({}));
        if (res.ok) feedback(`Envoyé : ${btn.textContent}`, 'success');
        else feedback(body.error || (body.errors || []).join(', ') || `Erreur ${res.status}`, 'error');
      } catch {
        feedback('API injoignable', 'error');
      } finally {
        btn.disabled = false;
      }
    });
  });

  // ---------- Chargement initial + temps réel ----------
  async function init() {
    try {
      cfg = await (await fetch('/api/v1/config')).json();
      $('group').textContent = `Groupe ${cfg.groupId.toUpperCase()}`;
      startVideo(cfg.videoUrl);

      const history = await (await fetch('/api/v1/telemetry?limit=' + MAX_POINTS)).json();
      history.forEach((t) => pushPoint(t, false));
      envChart.update(); gasChart.update();
      if (history.length) showKpis(history[history.length - 1]);

      const alerts = await (await fetch('/api/v1/alerts?limit=50')).json();
      alerts.reverse().forEach((a) => addAlert(a, false));
    } catch (e) {
      feedback('Impossible de charger les données initiales', 'error');
    }
  }

  const socket = io();
  socket.on('connect', () => setPill($('pill-socket'), true, 'Temps réel OK', 'Temps réel coupé'));
  socket.on('disconnect', () => setPill($('pill-socket'), false, 'Temps réel OK', 'Temps réel coupé'));
  socket.on('telemetry', (t) => { pushPoint(t); showKpis(t); });
  socket.on('alert', (a) => addAlert(a, true));
  socket.on('status', (s) => setPill($('pill-device'), s.online, 'Boîtier en ligne', 'Boîtier hors ligne'));

  async function pollHealth() {
    try {
      const h = await (await fetch('/api/v1/health')).json();
      setPill($('pill-mqtt'), h.mqtt, 'MQTT connecté', 'MQTT coupé');
    } catch {
      setPill($('pill-mqtt'), false, '', 'API injoignable');
    }
  }
  setInterval(pollHealth, 5000);

  init();
  pollHealth();
})();
