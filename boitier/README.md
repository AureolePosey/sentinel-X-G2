# Boîtier Sentinel-X : découpe laser, bois 3 mm, planches A4

![Boîtier assemblé](apercu_assemble.png)

Boîte de **185 × 110 × 80 mm** (intérieur 179 × 104 × 74 mm) en contreplaqué ou MDF de **3 mm**, assemblée par
**créneaux** (sans colle ni vis). Elle est autonome : la **batterie externe** est couchée au fond, la **breadboard
pleine longueur** collée dessus, le NodeMCU à l'avant droit ; le dessus s'emboîte et se retire pour la maintenance.

| Fichier | Rôle |
|---|---|
| `decoupe_A4_1.dxf` | planche A4 n° 1 : façade avant + dessus |
| `decoupe_A4_2.dxf` | planche A4 n° 2 : face arrière + fond |
| `decoupe_A4_3.dxf` | planche A4 n° 3 : côté gauche + côté droit |
| `decoupe_A4.png` | aperçu des trois planches |
| `decoupe_laser_3mm.svg` | les six panneaux sur une seule feuille (rouge = découpe, bleu = gravure) |
| `apercu_assemble.png`, `apercu_eclate.png` | illustrations |
| `generer_boitier_laser.py` | génère tous ces fichiers ; toutes les cotes sont réglables en tête de fichier |

Les DXF sont en **millimètres** (échelle 1:1), avec deux calques : **DECOUPE** (rouge) et **GRAVURE** (bleu, textes).
Chaque planche tient dans un A4 paysage (297 × 210 mm) avec 5 mm de marge.

## Composants pris en compte

Dimensions standard, à vérifier à la règle avant la découpe (puis ajuster le script et relancer) :

| Composant | Dimensions | Position |
|---|---|---|
| Batterie externe 10 000 mAh | ~140 × 70 × 15 mm | au fond, contre la paroi arrière et le côté droit |
| Breadboard pleine longueur | 165 × 55 × 9 mm | collée sur la batterie |
| NodeMCU ESP8266 | 58 × 31 mm | fond, avant droit, 4 entretoises M3 |
| Écran OLED 0,96" | fenêtre 26 × 15 mm | façade avant |
| PIR HC-SR501 | dôme Ø 23 mm | façade avant |
| MQ-2 | capteur Ø 20 mm | sous la grille du dessus |
| DHT22 | module | contre les fentes du côté gauche |

## Ouvertures

| Panneau | Ouverture | Composant |
|---|---|---|
| Avant | fenêtre 26 × 15 mm, Ø 23,6 mm, 2 × Ø 5,2 mm, grille 3 × 3 | écran, dôme du PIR, LED rouge / verte, buzzer |
| Avant | gravure | « SENTINEL-X » |
| Dessus | grille hexagonale Ø 22 mm, 8 fentes | capteur de gaz MQ-2, aération |
| Dessus | gravure | « SENTINEL-X · G2 », « GAZ » |
| Côté gauche | 6 fentes | DHT22 (air ambiant) |
| Côté droit | 13 × 8 mm | micro-USB du NodeMCU (programmation) |
| Côté droit | 16 × 10 mm | recharge de la batterie externe |
| Arrière | Ø 7 mm | passage de câble |
| Fond | 4 × Ø 3,2 mm | entretoises M3 du NodeMCU |

## Découpe

1. Importer chaque DXF dans le logiciel du laser (LightBurn, RDWorks, Inkscape) **en millimètres, sans redimensionner**.
2. Calque DECOUPE : coupe ; calque GRAVURE : gravure.
3. Essai sur une chute : deux créneaux doivent s'emboîter en force légère. Trop serré ou trop lâche : ajuster `KERF`
   (largeur du trait, 0,15 mm) ou `T` (épaisseur réelle mesurée), puis `python generer_boitier_laser.py`
   (`pip install manifold3d trimesh pillow ezdxf`).

## Montage

1. Visser le NodeMCU sur le fond (entretoises M3 de 6 mm), port USB face à la petite découpe du côté droit.
2. Poser la batterie au fond, port de recharge face à la grande découpe du côté droit ; coller la breadboard dessus.
3. Coller à chaud l'écran, le PIR et les LEDs derrière la façade, le DHT22 contre le côté gauche, le MQ-2 sous la grille du dessus.
4. Emboîter avant, côtés et arrière sur le fond, refermer avec le dessus.

Le modèle est vérifié par calcul : les six panneaux assemblés ne se chevauchent pas et ferment la boîte sans jour aux angles.
