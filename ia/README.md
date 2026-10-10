# Sentinel-X : intelligence artificielle

Deux scripts Python autonomes qui tournent sur le PC serveur et parlent à l'API (`docs/CONTRAT.md`).

| Script | Exigence du sujet | Ce qu'il fait |
|---|---|---|
| `vision.py` | Vision intelligente + optimisation des flux | Webcam → YOLOv8n → personnes encadrées → vidéo MJPEG `:5000/video` + alerte `human_detected` |
| `anomalies.py` | Maintenance prédictive | Télémétrie → Isolation Forest → alerte `anomaly` avant les seuils critiques |
| `common.py` | — | Lecture de `ia/.env` et envoi des alertes (`POST /api/v1/alerts`) |

## Installation

**Windows, en double-clic :** `lancer-ia.bat`. Au premier lancement, il crée l'environnement Python, installe les
bibliothèques (Internet nécessaire une fois) et ouvre `ia/.env` à remplir ; ensuite il lance `vision.py` et
`anomalies.py` dans deux fenêtres et ouvre la vidéo dans le navigateur.

Installation manuelle :

```bash
cd ia
python -m venv .venv
.venv\Scripts\activate            # Linux : source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env             # Linux : cp .env.example .env   puis remplir API_URL et API_KEY
```

Le modèle `models/yolov8n-320.onnx` (YOLOv8n exporté en ONNX, entrée 320 px) est fourni dans le dépôt.
Sans lui, `vision.py` bascule sur le détecteur de silhouettes HOG d'OpenCV (moins précis) au lieu de planter.

## Lancement

```bash
python vision.py        # vidéo : http://<serveur>:5000/video (affichée dans le dashboard)
python anomalies.py     # analyse la télémétrie toutes les 5 s
python anomalies.py --test   # démonstration sans serveur sur données synthétiques
```

## 1. Vision intelligente (`vision.py`)

- **Capture** dans un thread dédié qui ne garde que la dernière image (pas de retard qui s'accumule).
- **Bridage systématique** de chaque image en **640×480** avant traitement.
- **Inférence YOLOv8n** (format ONNX) avec le module DNN d'OpenCV, sur CPU : pas de PyTorch à installer sur le serveur.
  Entrée réduite à 320 px pour rester **sous 100 ms par image** ; le temps réel mesuré est incrusté sur la vidéo.
- Seule la classe COCO « person » est gardée, doublons supprimés par NMS (suppression des non-maxima).
- **Anti fausse alerte** : présence confirmée si une personne est vue sur 3 des 5 dernières images ;
  une alerte `human_detected` (critical) quand elle apparaît, au plus une toutes les 10 s, puis `state_change` quand elle part.
- **Flux MJPEG** sur le port 5000 (serveur HTTP de la bibliothèque standard), lu par le dashboard avec une balise `<img>`.
- Webcam débranchée : image « Caméra indisponible » et reconnexion automatique, le script ne s'arrête pas.

## 2. Maintenance prédictive (`anomalies.py`)

Pas de règle `if temp > 40` : un **Isolation Forest** (scikit-learn) apprend le comportement normal puis isole ce qui s'en écarte.

Chaque point analysé résume une **fenêtre glissante de 30 s** (15 mesures) :

| Caractéristique | Pourquoi |
|---|---|
| température, humidité, gaz | le niveau actuel |
| pente de température (°C/min, régression linéaire) | voir une **hausse lente** invisible sur une seule mesure |
| pente du gaz et écart-type du gaz | voir une **micro-dérive** du gaz bien avant le seuil critique |
| pente d'humidité | contexte |

- Apprentissage automatique dès 5 minutes de données, puis **réapprentissage toutes les 10 min** uniquement
  sur les fenêtres jugées normales (le modèle n'« apprend » pas la panne).
- Anomalie confirmée **2 analyses de suite** avant d'alerter ; message expliqué par les 2 caractéristiques
  les plus éloignées de l'habitude (en écarts-types σ).

Résultat de `python anomalies.py --test` :

```
- normal                                            -> 0 % de fenêtres anormales
- hausse lente de température + micro-dérive du gaz -> 96 % anormales (temp 23,3 °C, gaz 172 : seuils 40 °C / 400 loin)
- hausse lente de température seule                 -> 83 % anormales
```

C'est l'exemple du sujet : une **corrélation suspecte entre une hausse lente de température et une micro-déviation
de gaz est détectée avant que le seuil d'alerte critique ne soit atteint**.

## Licence du modèle

YOLOv8 (Ultralytics) est distribué sous licence AGPL-3.0, compatible avec un projet pédagogique au code ouvert.
