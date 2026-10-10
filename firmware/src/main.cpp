/*
 * Sentinel-X : firmware ESP8266
 * - lit DHT22 (température/humidité), MQ-2 (gaz) et PIR (présence)
 * - affiche l'état sur l'écran OLED
 * - publie la télémétrie en JSON via MQTT (option TLS)
 * - exécute les commandes reçues (buzzer, LEDs)
 * - se reconnecte tout seul au WiFi et au broker, sans jamais bloquer la boucle
 *
 * Câblage (NodeMCU) :
 *   OLED SDA -> D2   OLED SCL -> D1   (I2C, adresse 0x3C, alim 3V3)
 *   DHT22 DATA -> D5 (résistance 10k entre DATA et 3V3 si module nu)
 *   PIR OUT -> D6    (alim VIN 5V)
 *   MQ-2 AO -> A0    (alim VIN 5V, via pont diviseur 10k/20k pour ne pas dépasser 3,3 V)
 *   Buzzer + -> D7
 *   LED rouge -> D0 (via 220 ohms)   LED verte -> D8 (via 220 ohms)
 */
#include <Arduino.h>
#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <time.h>

#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "Copie include/secrets.example.h en include/secrets.h et remplis-le."
#endif

// ---------- Broches ----------
#define PIN_DHT      D5
#define PIN_PIR      D6
#define PIN_BUZZER   D7
#define PIN_LED_RED  D0
#define PIN_LED_GRN  D8
#define PIN_GAS      A0

// ---------- Réglages ----------
const unsigned long PUBLISH_EVERY_MS = 2000;  // une mesure toutes les 2 s
const unsigned long OLED_EVERY_MS    = 500;
const int GAS_LOCAL_ALARM            = 400;   // seuil d'alerte locale (LED rouge)

// ---------- Objets ----------
DHT dht(PIN_DHT, DHT22);
Adafruit_SSD1306 oled(128, 64, &Wire, -1);
bool oledOk = false;

#ifdef USE_TLS
#include <WiFiClientSecure.h>
BearSSL::WiFiClientSecure net;
BearSSL::X509List caCert(MQTT_CA_CERT);
#else
WiFiClient net;
#endif
PubSubClient mqtt(net);

String topicTelemetry, topicStatus, topicCmd, clientId;

// ---------- État ----------
float lastTemp = NAN, lastHum = NAN;
int lastGas = 0;
bool lastMotion = false;
bool buzzerOn = false, ledRedForced = false;
// LED verte : automatique au démarrage (témoin "tout va bien"), puis le dashboard a le dernier mot
enum GreenMode { GREEN_AUTO, GREEN_ON, GREEN_OFF };
GreenMode ledGreenMode = GREEN_AUTO;
unsigned long beepUntil = 0;
unsigned long lastPublish = 0, lastOled = 0, lastMqttTry = 0;

// ---------- Actionneurs ----------
void applyOutputs() {
  static bool buzzing = false;
  bool wantBuzz = buzzerOn || millis() < beepUntil;
  if (wantBuzz != buzzing) { // on ne touche au buzzer que s'il change d'état
    buzzing = wantBuzz;
    if (buzzing) tone(PIN_BUZZER, 2000);
    else noTone(PIN_BUZZER);
  }

  // LED rouge : demandée par le dashboard OU gaz détecté (un "off" ne masque jamais une vraie fuite).
  // Le PIR n'allume pas la LED : il est signalé sur l'écran et le dashboard.
  bool gasAlarm = lastGas >= GAS_LOCAL_ALARM;
  digitalWrite(PIN_LED_RED, (ledRedForced || gasAlarm) ? HIGH : LOW);
  bool greenAuto = !gasAlarm && mqtt.connected();
  bool green = ledGreenMode == GREEN_ON || (ledGreenMode == GREEN_AUTO && greenAuto);
  digitalWrite(PIN_LED_GRN, green ? HIGH : LOW);
}

void onCommand(char* topic, byte* payload, unsigned int length) {
  if (length > 200) return; // message anormal ignoré
  JsonDocument doc;
  if (deserializeJson(doc, payload, length)) {
    Serial.println(F("[cmd] JSON invalide"));
    return;
  }
  const char* target = doc["target"] | "";
  const char* action = doc["action"] | "";
  Serial.printf("[cmd] %s -> %s\n", target, action);

  bool on = strcmp(action, "on") == 0;
  if (strcmp(target, "buzzer") == 0) {
    if (strcmp(action, "beep") == 0) beepUntil = millis() + 400;
    else buzzerOn = on;
  } else if (strcmp(target, "led_red") == 0) {
    ledRedForced = on;
  } else if (strcmp(target, "led_green") == 0) {
    ledGreenMode = on ? GREEN_ON : GREEN_OFF;
  } else if (strcmp(target, "all") == 0) {
    buzzerOn = ledRedForced = false;
    ledGreenMode = GREEN_OFF;
    beepUntil = 0;
  }
  applyOutputs();
}

// ---------- Réseau ----------
const char* wifiStatusText(wl_status_t s) {
  switch (s) {
    case WL_CONNECTED:      return "connecté";
    case WL_NO_SSID_AVAIL:  return "réseau introuvable (nom faux ou réseau 5 GHz ?)";
    case WL_WRONG_PASSWORD: return "mot de passe refusé";
    case WL_CONNECT_FAILED: return "échec de connexion";
    case WL_DISCONNECTED:   return "déconnecté";
    case WL_IDLE_STATUS:    return "en attente";
    default:                return "en cours";
  }
}

// Diagnostic au démarrage : liste les réseaux 2,4 GHz visibles (environ 2 s, une seule fois).
void scanWifi() {
  int n = WiFi.scanNetworks();
  bool found = false;
  Serial.printf("[wifi] %d réseau(x) 2,4 GHz visible(s) :\n", n);
  for (int i = 0; i < n; i++) {
    bool same = WiFi.SSID(i) == WIFI_SSID;
    found |= same;
    Serial.printf("   %s %-24s %4d dBm  canal %2d  %s\n", same ? ">" : " ", WiFi.SSID(i).c_str(),
                  WiFi.RSSI(i), WiFi.channel(i), WiFi.encryptionType(i) == ENC_TYPE_NONE ? "ouvert" : "protégé");
  }
  if (!found) Serial.printf("[wifi] \"%s\" n'est PAS visible : vérifie le nom ou passe en 2,4 GHz\n", WIFI_SSID);
  WiFi.scanDelete();
}

void setupWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);
  scanWifi();
#ifdef STATIC_IP
  // IP fixe fournie par l'équipe cloud (sinon le routeur en attribue une automatiquement)
  IPAddress ip, gw, mask;
  ip.fromString(STATIC_IP); gw.fromString(STATIC_GATEWAY); mask.fromString(STATIC_SUBNET);
  WiFi.config(ip, gw, mask, gw);
  Serial.printf("[wifi] IP fixe %s\n", STATIC_IP);
#endif
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("[wifi] connexion à %s...\n", WIFI_SSID);
#ifdef NTP_SERVER
  // Heure réseau (UTC) : sert à vérifier la date de validité du certificat TLS
  configTime(0, 0, NTP_SERVER);
#endif
}

// Affiche chaque changement d'état WiFi dans le moniteur série.
void watchWifi() {
  static wl_status_t lastStatus = WL_IDLE_STATUS;
  wl_status_t s = WiFi.status();
  if (s == lastStatus) return;
  lastStatus = s;
  if (s == WL_CONNECTED) {
    Serial.printf("[wifi] connecté, IP %s, signal %d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  } else {
    Serial.printf("[wifi] état : %s\n", wifiStatusText(s));
  }
}

#ifdef USE_TLS
// BearSSL a besoin de l'heure pour vérifier la validité du certificat.
// On prend l'heure NTP si elle est arrivée, sinon la date de compilation (flasher APRÈS la création des certificats).
time_t compileTime() {
  const char* months = "JanFebMarAprMayJunJulAugSepOctNovDec";
  char m[4]; int d, y, hh, mm, ss;
  sscanf(__DATE__, "%3s %d %d", m, &d, &y);
  sscanf(__TIME__, "%d:%d:%d", &hh, &mm, &ss);
  struct tm t = {};
  t.tm_year = y - 1900; t.tm_mon = (strstr(months, m) - months) / 3; t.tm_mday = d;
  t.tm_hour = hh; t.tm_min = mm; t.tm_sec = ss;
  return mktime(&t);
}

void setTlsTime() {
  time_t now = time(nullptr);
  bool ntpOk = now > 1700000000; // après nov. 2023 : l'heure NTP est arrivée
  net.setX509Time(ntpOk ? now : compileTime());
  Serial.printf("[tls] heure utilisée : %s\n", ntpOk ? "NTP" : "date de compilation");
}
#endif

void tryMqtt() {
  if (WiFi.status() != WL_CONNECTED || mqtt.connected()) return;
  if (millis() - lastMqttTry < 3000) return; // une tentative toutes les 3 s, sans bloquer
  lastMqttTry = millis();

  Serial.printf("[mqtt] connexion à %s:%d...\n", MQTT_HOST, MQTT_PORT);
#ifdef USE_TLS
  setTlsTime();
#endif
  // Dernière volonté (LWT) : si le boîtier disparaît, le broker publie "offline"
  bool ok = strlen(MQTT_USER) > 0
    ? mqtt.connect(clientId.c_str(), MQTT_USER, MQTT_PASS, topicStatus.c_str(), 1, true, "offline")
    : mqtt.connect(clientId.c_str(), topicStatus.c_str(), 1, true, "offline");

  if (ok) {
    Serial.println(F("[mqtt] connecté"));
    mqtt.publish(topicStatus.c_str(), "online", true);
    mqtt.subscribe(topicCmd.c_str(), 1);
  } else {
    Serial.printf("[mqtt] échec, code %d\n", mqtt.state());
#ifdef USE_TLS
    char err[96];
    if (net.getLastSSLError(err, sizeof(err))) Serial.printf("[tls] erreur : %s\n", err);
#endif
  }
}

// ---------- Capteurs ----------
void readSensors() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  if (!isnan(t)) lastTemp = t; // on garde la dernière valeur valide
  if (!isnan(h)) lastHum = h;
  lastGas = analogRead(PIN_GAS);
  lastMotion = digitalRead(PIN_PIR) == HIGH;
}

void publishTelemetry() {
  JsonDocument doc;
  doc["device"] = String("sentinel-") + GROUP_ID;
  if (isnan(lastTemp)) doc["temp"] = nullptr; else doc["temp"] = round(lastTemp * 10) / 10.0;
  if (isnan(lastHum)) doc["hum"] = nullptr; else doc["hum"] = round(lastHum * 10) / 10.0;
  doc["gas"] = lastGas;
  doc["motion"] = lastMotion;
  doc["rssi"] = WiFi.RSSI();
  doc["uptime"] = millis() / 1000;

  char buf[200];
  size_t n = serializeJson(doc, buf);
  bool ok = mqtt.publish(topicTelemetry.c_str(), (const uint8_t*)buf, n, false);
  Serial.printf("[pub] %s %s\n", ok ? "OK" : "ECHEC", buf);
}

// ---------- Écran ----------
void drawOled() {
  if (!oledOk) return;
  oled.clearDisplay();
  oled.setTextSize(1);
  oled.setTextColor(SSD1306_WHITE);
  oled.setCursor(0, 0);
  oled.printf("SENTINEL-X  %s\n", GROUP_ID);
  oled.drawFastHLine(0, 9, 128, SSD1306_WHITE);
  oled.setCursor(0, 12);
  if (WiFi.status() == WL_CONNECTED) oled.printf("IP %s\n", WiFi.localIP().toString().c_str());
  else oled.println("WiFi: connexion...");
  oled.printf("MQTT: %s\n", mqtt.connected() ? "OK" : "--");
  if (isnan(lastTemp)) oled.println("T: --  H: --");
  else oled.printf("T:%.1fC  H:%.0f%%\n", lastTemp, lastHum);
  oled.printf("Gaz: %d\n", lastGas);
  oled.printf("PIR: %s\n", lastMotion ? "MOUVEMENT" : "calme");
  if (buzzerOn || lastGas >= GAS_LOCAL_ALARM) {
    oled.setCursor(0, 56);
    oled.print("!! ALERTE !!");
  }
  oled.display();
}

// ---------- Programme ----------
void setup() {
  Serial.begin(115200);
  delay(100);
  Serial.println(F("\n=== Sentinel-X ==="));

  pinMode(PIN_PIR, INPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_LED_RED, OUTPUT);
  pinMode(PIN_LED_GRN, OUTPUT);
  noTone(PIN_BUZZER);

  Wire.begin(D2, D1);
  // oled.begin() répond "OK" même sans écran : on vérifie d'abord qui répond sur le bus I2C.
  uint8_t oledAddr = 0;
  Serial.print(F("[i2c] appareils trouvés :"));
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      Serial.printf(" 0x%02X", a);
      if (a == 0x3C || a == 0x3D) oledAddr = a;
    }
  }
  Serial.println();
  oledOk = oledAddr && oled.begin(SSD1306_SWITCHCAPVCC, oledAddr);
  if (oledOk) Serial.printf("[oled] écran OK à l'adresse 0x%02X\n", oledAddr);
  else Serial.println(F("[oled] écran introuvable : vérifie VCC->3V3, GND->G, SDA->D2, SCL->D1"));
  drawOled();

  dht.begin();

  topicTelemetry = String("sentinel/") + GROUP_ID + "/telemetry";
  topicStatus    = String("sentinel/") + GROUP_ID + "/status";
  topicCmd       = String("sentinel/") + GROUP_ID + "/cmd";
  clientId       = String("sentinel-") + GROUP_ID + "-" + String(ESP.getChipId(), HEX);

#ifdef USE_TLS
  net.setTrustAnchors(&caCert);
  // Le nom dans le certificat du broker doit correspondre à MQTT_HOST (ou son IP en SAN).
#endif
  // Si MQTT_HOST est une IP, on se connecte à l'IP : BearSSL ne sait pas comparer une IP aux adresses
  // du certificat (il ne lit que les noms DNS). La chaîne reste vérifiée avec notre CA privée,
  // qui ne signe que le certificat du serveur : seul notre broker est accepté.
  static IPAddress brokerIp;
  if (brokerIp.fromString(MQTT_HOST)) mqtt.setServer(brokerIp, MQTT_PORT);
  else mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onCommand);
  mqtt.setBufferSize(512);
  mqtt.setKeepAlive(15);

  setupWifi();
}

void loop() {
  watchWifi();
  tryMqtt();
  mqtt.loop();

  unsigned long now = millis();
  if (now - lastPublish >= PUBLISH_EVERY_MS) {
    lastPublish = now;
    readSensors();
    if (mqtt.connected()) publishTelemetry();
  }
  if (now - lastOled >= OLED_EVERY_MS) {
    lastOled = now;
    drawOled();
  }
  applyOutputs();
}
