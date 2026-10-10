#!/bin/sh
# Surveillance MCO du serveur Sentinel-X : CPU / RAM / disque de la machine hôte, consommation de chaque
# conteneur et taille des données et journaux Mosquitto, face à l'afflux continu de messages MQTT.
#
# Usage (depuis infra/) :
#   sudo ./monitoring.sh            une mesure toutes les 60 s, ajoutée à monitoring/metrics.csv
#   sudo ./monitoring.sh 10         une mesure toutes les 10 s
#   sudo ./monitoring.sh once       une seule mesure affichée à l'écran (pour une capture)
# Le fichier est limité aux 10 000 dernières lignes (environ 1 semaine à 60 s) : il ne remplit pas le disque.
set -u
cd "$(dirname "$0")"
INTERVAL="${1:-60}"
OUT=monitoring/metrics.csv
MAX_LINES=10000
mkdir -p monitoring

measure() {
  now=$(date '+%Y-%m-%d %H:%M:%S')
  load=$(cut -d' ' -f1 /proc/loadavg)
  mem=$(free -m | awk '/^Mem:/ {printf "%d/%dMo (%.0f%%)", $3, $2, $3*100/$2}')
  disk=$(df -h / | awk 'NR==2 {print $5}')
  mosq_data=$(du -sh mosquitto/data 2>/dev/null | cut -f1)
  # Taille des journaux Docker (limités à 3 x 10 Mo par conteneur dans docker-compose.yml)
  logs=$(docker ps -q --filter "label=com.docker.compose.project=sentinel" \
    | xargs -r docker inspect --format '{{.LogPath}}' 2>/dev/null | xargs -r du -ch 2>/dev/null | tail -1 | cut -f1)
  stats=$(docker stats --no-stream --format '{{.Name}}={{.CPUPerc}} {{.MemUsage}}' \
    $(docker ps -q --filter "label=com.docker.compose.project=sentinel") 2>/dev/null | sed 's/ \/ [^ ]*//' | tr '\n' ';')
  echo "$now,charge=$load,ram=$mem,disque=$disk,mosquitto_data=${mosq_data:-?},journaux_docker=${logs:-?},$stats"
}

if [ "$INTERVAL" = "once" ]; then
  measure | tr ',;' '\n\n'
  exit 0
fi

echo "Mesure toutes les ${INTERVAL} s dans infra/$OUT (Ctrl+C pour arrêter)"
while true; do
  line=$(measure)
  echo "$line"
  echo "$line" >> "$OUT"
  tail -n "$MAX_LINES" "$OUT" > "$OUT.tmp" && mv "$OUT.tmp" "$OUT"
  sleep "$INTERVAL"
done
