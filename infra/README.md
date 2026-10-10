# Serveur Sentinel-X (VM de l'équipe cloud)

Trois services Docker : **mosquitto** (MQTT, TLS sur 8883), **db** (PostgreSQL, réseau interne),
**api** (API REST + Socket.io + dashboard sur le port 3000).

```
ESP8266 ──TLS 8883──► mosquitto ──1883 (réseau Docker interne)──► api ──► db
Navigateur / IA ──────────── HTTP 3000 ──────────────────────────► api
```

## Fichiers à créer sur le serveur (ignorés par Git)

Depuis le dossier `infra/` :

```bash
# 1. Secrets (une valeur par fichier)
mkdir -p secrets
openssl rand -hex 24 > secrets/api_key.txt            # clé API : à donner au dashboard et à l'IA
openssl rand -hex 16 > secrets/mqtt_api_password.txt  # compte Mosquitto "api"
# secrets/db_password.txt : garder celui qui existe déjà (sinon la base existante refuse la connexion)

# 2. Comptes Mosquitto : esp01 (boîtier) + api (le mot de passe de secrets/mqtt_api_password.txt)
sudo docker run --rm -v "$PWD/mosquitto/config:/c" eclipse-mosquitto:2 \
  mosquitto_passwd -b /c/passwd api "$(cat secrets/mqtt_api_password.txt)"

# 3. ACL : partir du modèle
cp mosquitto/config/acl.example mosquitto/config/acl

# 4. Droits : Mosquitto tourne en utilisateur 1883
sudo chown -R 1883:1883 mosquitto/config mosquitto/certs mosquitto/data
```

Certificats attendus dans `mosquitto/certs/` : `ca.crt`, `server.crt` (avec l'IP du serveur en SAN), `server.key`.
Voir `docs/TLS.md`.

## Lancer et vérifier

```bash
sudo docker compose up -d --build
sudo docker compose ps          # api (healthy), db (healthy), mosquitto (healthy)
sudo docker compose logs api    # "[db] stockage : postgresql" puis "[mqtt] connecté"
```

Dashboard : http://192.168.10.1:3000

## Sécurité (pour le rapport)

- Seuls **8883** (MQTT chiffré) et **3000** (API) sont publiés, et uniquement sur l'IP du WiFi de table.
- 1883 est interne au réseau Docker (API ↔ broker sur la même machine) ; PostgreSQL est sur un réseau `internal`.
- Mosquitto : pas d'anonyme, mot de passe par compte, ACL au moindre privilège (le boîtier ne peut pas s'envoyer de commandes).
- Secrets Docker (fichiers) au lieu de variables d'environnement ; conteneurs `read_only`, `cap_drop: ALL`,
  `no-new-privileges`, limites mémoire, journaux limités en taille.
- Test d'attaque de l'API : `node ../tools/pentest-api.js "$(cat secrets/api_key.txt)" http://192.168.10.1:3000`
  (depuis `api/`, après `npm install`; l'inondation bloque l'API 1 minute : pas pendant une démo).

## Monitoring & MCO

```bash
chmod +x monitoring.sh
sudo ./monitoring.sh once     # photo instantanée (pour une capture d'écran)
sudo ./monitoring.sh          # une mesure par minute dans infra/monitoring/metrics.csv (10 000 lignes max)
sudo docker stats             # vue temps réel CPU / RAM par conteneur
```

Garde-fous déjà en place : `mem_limit` par conteneur, journaux Docker limités à 3 x 10 Mo par conteneur,
`max_queued_messages` et `message_size_limit` dans Mosquitto, `restart: unless-stopped` et healthchecks.

## Audit réseau du 7 octobre (depuis le WiFi de table, 192.168.10.30)

| Machine | Ports TCP joignables | Commentaire |
|---|---|---|
| VM serveur 192.168.10.1 | 3000, 8883 | conforme : SSH, PostgreSQL et 1883 invisibles |
| Routeur 192.168.10.254 | 22, 80, 443 | interface d'administration exposée : mot de passe fort, SSH du routeur désactivé si inutile |

Suites données à l'audit (corrections et risque accepté) :

| Constat | Décision |
|---|---|
| Mot de passe du WiFi trop facile à deviner | **corrigé** : mot de passe du WiFi changé |
| Administration du routeur exposée sur le WiFi (22/80/443) | **corrigé** : SSH du point d'accès supprimé |
| Accès SSH au serveur | **corrigé** : service SSH supprimé de la VM ; pare-feu au strict nécessaire (3000 et 8883 en entrée) |
| API en HTTP : la clé API circule en clair sur le WiFi | accepté : le trafic WiFi est chiffré par WPA2 ; en production : HTTPS (proxy inverse TLS) |
