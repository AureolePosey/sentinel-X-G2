# Chiffrement TLS (MQTTS) entre l'ESP8266 et le serveur

Objectif du sujet : les trames du boîtier ESP8266 vers la stack conteneurisée doivent être chiffrées de bout en bout.

```
ESP8266 192.168.10.20 ──MQTTS (TLS 1.2, port 8883)──► Mosquitto (VM 192.168.10.1)
                                                        │ 1883 interne au réseau Docker (non publié)
                                                        ▼
                                                       API
```

## 1. Autorité de certification et certificat du broker (VM serveur, `infra/mosquitto/certs/`)

```bash
# Autorité de certification privée du groupe (RSA 4096, 1 an)
openssl req -x509 -newkey rsa:4096 -nodes -days 365 \
  -keyout ca.key -out ca.crt -subj "/CN=Sentinel-X CA"

# Certificat du broker signé par la CA, avec l'IP du serveur en subjectAltName
openssl req -newkey rsa:2048 -nodes -keyout server.key -out server.csr -subj "/CN=192.168.10.1"
printf "subjectAltName=IP:192.168.10.1" > san.ext
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -days 365 -extfile san.ext
```

`ca.key` et `server.key` sont des secrets : jamais dans Git (`.gitignore`), droits restreints à l'utilisateur
Mosquitto (`chown 1883:1883`). Seul `ca.crt` (public) est donné au boîtier.

## 2. Mosquitto (`infra/mosquitto/config/mosquitto.conf`)

- `listener 8883` avec `cafile`, `certfile`, `keyfile`, `tls_version tlsv1.2` : seul port publié, et uniquement sur `192.168.10.1`.
- `listener 1883` : réservé à l'API sur le réseau Docker interne (non publié dans `docker-compose.yml`).
- `allow_anonymous false`, `password_file` (comptes `esp01` et `api`), `acl_file` (moindre privilège).

## 3. ESP8266 (`firmware/`)

- `build_flags = -D USE_TLS` dans `platformio.ini` (activé).
- `firmware/include/secrets.h` : contenu de `ca.crt` dans `MQTT_CA_CERT`, `MQTT_PORT 8883`, identifiants `esp01`.
- Vérification de la date du certificat : heure NTP fournie par la VM (`192.168.10.1`), date de compilation en secours.
- La bibliothèque BearSSL de l'ESP8266 ne compare le nom du serveur qu'aux noms DNS du certificat, pas aux adresses IP :
  le firmware se connecte donc par adresse IP et valide la **chaîne de certificats avec la CA privée**,
  qui ne signe que le certificat du broker. Un faux broker est refusé (`self-signed certificate in certificate chain`).

## 4. Preuve du chiffrement (Wireshark)

Capture sur l'interface WiFi du serveur :
- avant TLS, filtre `tcp.port == 1883` : le JSON de télémétrie (`"temp":21.6, "gas":…`) est lisible en clair ;
- après TLS, filtre `tcp.port == 8883` : seuls des enregistrements `TLSv1.2 Application Data` illisibles.

Contrôles complémentaires réalisés :
- connexion anonyme sur 8883 : refusée (`Not authorized`) ;
- mauvais mot de passe : refusé ;
- client TLS sans la CA du groupe : refusé ;
- le compte `esp01` ne peut pas publier sur le topic des commandes (ACL).
