// MODÈLE de fichier de secrets.
// 1. Copie ce fichier en "secrets.h" dans le même dossier.
// 2. Remplis les valeurs.
// secrets.h est dans le .gitignore : il ne doit JAMAIS être commité.
#pragma once

// --- WiFi de la table (routeur fourni par l'équipe cloud) ---
#define WIFI_SSID     "nom-du-wifi"
#define WIFI_PASSWORD "mot-de-passe-wifi"

// --- IP fixe du boîtier (optionnel : commente ces 3 lignes pour une IP automatique) ---
#define STATIC_IP      "192.168.10.20"
#define STATIC_GATEWAY "192.168.10.1"
#define STATIC_SUBNET  "255.255.255.0"

// --- Serveur de temps NTP du réseau de table (sert à vérifier le certificat TLS) ---
#define NTP_SERVER    "192.168.10.1"

// --- Broker MQTT (IP du PC serveur) ---
#define MQTT_HOST     "192.168.10.1"
#define MQTT_PORT     8883          // 8883 avec TLS (USE_TLS), 1883 sans
#define MQTT_USER     ""            // identifiants Mosquitto fournis par l'équipe cloud
#define MQTT_PASS     ""

// --- Identifiant du groupe (topics sentinel/<GROUP_ID>/...) ---
#define GROUP_ID      "g2"

#ifdef USE_TLS
// Certificat de l'autorité (CA) fourni par l'équipe cloud : contenu complet du fichier ca.crt
// (il est public, mais on le garde ici avec le reste de la configuration du réseau)
static const char MQTT_CA_CERT[] PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
COLLE ICI LE CONTENU DE ca.crt
-----END CERTIFICATE-----
)EOF";
#endif
