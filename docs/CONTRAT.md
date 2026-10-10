# Contrat de données Sentinel-X

Ce document fixe **comment les briques se parlent**. Toute l'équipe (DEV, IA, CLOUD) s'y réfère.
Si quelque chose change ici, on prévient tout le monde.

`<g>` = identifiant du groupe, ici `g2` (groupe 2). Il est réglé par la variable `GROUP_ID`.

---

## 1. Adresses et ports (PC serveur)

| Service | Port | Qui s'y connecte |
|---|---|---|
| Mosquitto (MQTTS, TLS) | 8883 | ESP8266 (compte `esp01`) |
| Mosquitto interne | 1883 | API uniquement, réseau Docker (non publié) |
| API + dashboard | 3000 | Navigateur, scripts IA |
| Flux vidéo IA (MJPEG) | 5000 | Navigateur (balise `<img>`), sur la machine qui fait tourner `ia/vision.py` |
| Base de données PostgreSQL | 5432 | API uniquement, réseau Docker interne (jamais exposée) |

### Plan d'adressage : WiFi de table `Sentinel-X-G2` (WPA2, 2,4 GHz), `192.168.10.0/24`, sans accès Internet

| Adresse | Machine | Attribution |
|---|---|---|
| `192.168.10.1` | VM serveur (Docker : Mosquitto, PostgreSQL, API) | fixe, carte réseau en mode pont |
| `192.168.10.10` | PC hôte de la VM : scripts IA (`ia/lancer-ia.bat`) + webcam USB, vidéo sur `:5000` | fixe |
| `192.168.10.20` | Boîtier ESP8266 | fixe (firmware) |
| `192.168.10.30` | Poste DEV : développement, flash du boîtier, secours IA | fixe, sans passerelle |
| `192.168.10.254` | Routeur WiFi (point d'accès) | fixe |

Le serveur NTP et le DHCP sont fournis par la VM (`192.168.10.1`).
Sur le serveur, seuls **8883** et **3000** sont joignables depuis le WiFi (vérifié par scan le 7 octobre).

---

## 2. Topics MQTT

| Topic | Sens | Contenu | Retenu |
|---|---|---|---|
| `sentinel/<g>/telemetry` | ESP8266 → serveur | mesures, toutes les 2 s | non |
| `sentinel/<g>/status` | ESP8266 → serveur | `online` / `offline` (LWT) | oui |
| `sentinel/<g>/cmd` | serveur → ESP8266 | commande actionneur | non |

### Télémétrie (`sentinel/<g>/telemetry`)

```json
{
  "device": "sentinel-g2",
  "temp": 24.5,
  "hum": 51.2,
  "gas": 312,
  "motion": false,
  "rssi": -58,
  "uptime": 1234
}
```

| Champ | Type | Unité / plage |
|---|---|---|
| `device` | texte | identifiant du boîtier |
| `temp` | nombre ou `null` | °C (null si le DHT22 ne répond pas) |
| `hum` | nombre ou `null` | % |
| `gas` | entier | 0 à 1023 (valeur brute de A0) |
| `motion` | booléen | `true` = mouvement détecté |
| `rssi` | entier | qualité WiFi en dBm |
| `uptime` | entier | secondes depuis le démarrage |

L'horodatage est ajouté **par le serveur** à la réception (l'ESP8266 n'a pas d'horloge fiable).

### Commande (`sentinel/<g>/cmd`)

```json
{ "target": "buzzer", "action": "on" }
```

| `target` | `action` possibles |
|---|---|
| `buzzer` | `on`, `off`, `beep` |
| `led_red` | `on`, `off` |
| `led_green` | `on`, `off` |
| `all` | `off` (tout couper) |

---

## 3. API REST (`http://<pc-serveur>:3000/api/v1`)

Les routes marquées 🔑 exigent l'en-tête `X-API-Key: <clé>` (clé dans le `.env`, jamais dans Git).

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/health` | l'API répond ? |
| GET | `/status` | boîtier en ligne, dernière mesure, alertes actives |
| GET | `/telemetry?limit=100` | dernières mesures (pour les courbes) |
| GET | `/alerts?limit=50` | historique des alertes |
| POST 🔑 | `/alerts` | **route obligatoire** : recevoir une alerte |
| POST 🔑 | `/commands` | envoyer une commande au boîtier |
| GET | `/config` | réglages utiles au dashboard (URL vidéo…) |

### `POST /api/v1/alerts` (format obligatoire)

```json
{
  "source": "ia-vision",
  "type": "human_detected",
  "level": "critical",
  "message": "Présence humaine détectée (confiance 0.87)",
  "data": { "confidence": 0.87 }
}
```

| Champ | Obligatoire | Valeurs |
|---|---|---|
| `source` | oui | `esp8266`, `ia-vision`, `ia-anomaly`, `api`, `dashboard` |
| `type` | oui | `gas_detected`, `motion_detected`, `temp_high`, `human_detected`, `anomaly`, `device_offline`, `device_online`, `state_change` |
| `level` | oui | `info`, `warning`, `critical` |
| `message` | non | texte, 300 caractères max |
| `data` | non | objet libre (petit) |

Réponse `201` : l'alerte enregistrée, avec son `id` et son `ts`.
Réponse `400` : la liste des erreurs de validation. Réponse `401` : clé absente ou fausse.

Exemple pour l'équipe IA (Python) :

```python
import requests
requests.post(
    "http://192.168.10.1:3000/api/v1/alerts",
    headers={"X-API-Key": API_KEY},
    json={"source": "ia-vision", "type": "human_detected", "level": "critical",
          "message": "Intrus détecté", "data": {"confidence": 0.87}},
    timeout=2,
)
```

L'équipe IA peut aussi **lire la télémétrie** pour son modèle d'anomalies :
soit en s'abonnant au topic MQTT `sentinel/<g>/telemetry`, soit avec `GET /api/v1/telemetry?limit=500`.

### `POST /api/v1/commands`

```json
{ "target": "buzzer", "action": "on" }
```

---

## 4. Temps réel (Socket.io, même adresse que l'API)

| Événement | Contenu |
|---|---|
| `telemetry` | une mesure (avec `ts`) |
| `alert` | une alerte |
| `status` | `{ online, lastSeen }` |

---

## 5. Flux vidéo

Le script IA diffuse l'image annotée (cadres YOLO) en **MJPEG** sur `http://<pc-serveur>:5000/video`.
Le dashboard l'affiche avec une simple balise `<img>`. L'URL est réglée par `VIDEO_URL` dans le `.env` de l'API.
