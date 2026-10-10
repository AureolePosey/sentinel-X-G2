"""
Boîtier Sentinel-X en bois (contreplaqué ou MDF 3 mm) pour découpe laser, assemblage par créneaux.

Génère :
  decoupe_A4_1.dxf, decoupe_A4_2.dxf, decoupe_A4_3.dxf   les 6 panneaux sur 3 planches A4 (calques DECOUPE et GRAVURE, mm)
  decoupe_A4.png          aperçu des 3 planches
  decoupe_laser_3mm.svg   les 6 panneaux sur une seule feuille (rouge = découpe, bleu = gravure), cotes en millimètres
  apercu_assemble.png     la boîte montée, ouvertures légendées
  apercu_eclate.png       la boîte éclatée (montage)

Usage : pip install manifold3d trimesh pillow ezdxf ; python generer_boitier_laser.py
Toutes les cotes sont en millimètres, regroupées ci-dessous : mesurez vos modules et ajustez avant de découper.
"""
import os

import numpy as np
import trimesh
from manifold3d import CrossSection, JoinType, Manifold

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- Matière et dimensions extérieures
T = 3.0              # épaisseur du bois
KERF = 0.15          # largeur du trait laser (compensée : les créneaux serrent juste)
W, D, H = 185.0, 110.0, 80.0   # largeur (X), profondeur (Y), hauteur (Z) : breadboard pleine longueur posée sur la batterie
CRENEAU = 15.0       # largeur visée d'un créneau

# ---------------------------------------------------------------- Façade avant (vue de l'extérieur, u = X, v = Z)
OLED = dict(u=20, v=46, w=26, h=15)              # fenêtre de l'écran 0,96" (coin bas gauche)
PIR = dict(u=92, v=44, r=11.8)                   # dôme du PIR HC-SR501 (23 mm)
LEDS = [dict(u=145, v=56), dict(u=160, v=56)]    # LED rouge, LED verte (5 mm)
LED_R = 2.6
BUZZER = dict(u=152, v=30, pas=4.0, r=1.1)       # grille 3 x 3 devant le buzzer
GRAVURE_AVANT = dict(u=12, v=10, texte="SENTINEL-X", taille=7)

# ---------------------------------------------------------------- Côtés (u = Y depuis l'avant, v = Z)
USB = dict(u=19, v=12, w=13, h=8)                # côté droit : micro-USB du NodeMCU (programmation)
CHARGE = dict(u=72, v=10.5, w=16, h=10)          # côté droit : recharge de la batterie externe
DHT_FENTES = dict(u0=62, n=6, pas=6, w=2.4, v0=30, h=30)   # côté gauche : aération du DHT22
CABLE = dict(u=W / 2, v=14, r=3.5)               # face arrière : passage de câble

# ---------------------------------------------------------------- Dessus (u = X, v = Y depuis l'avant)
MQ2 = dict(u=42, v=70, r=11.0, trou=1.3, pas=3.4)          # grille au-dessus du capteur de gaz
AERATION = dict(u0=110, v=70, n=8, pas=6, l=28, w=2.4)     # fentes d'aération
GRAVURE_DESSUS = [dict(u=12, v=18, texte="SENTINEL-X · G2", taille=8), dict(u=30, v=88, texte="GAZ", taille=5)]

# ---------------------------------------------------------------- Fond : fixation du NodeMCU (entretoises M3)
NODEMCU = dict(u=149, v=19, ecart=(52.0, 25.5), trou=1.6)   # à l'avant droit ; la batterie occupe l'arrière du fond
# Composants pris en compte (dimensions standard, à vérifier à la règle) :
#   batterie externe 10 000 mAh ~140 x 70 x 15 mm, à plat au fond, contre la paroi arrière et le côté droit
#   breadboard pleine longueur 165 x 55 x 9 mm, collée sur la batterie ; NodeMCU 58 x 31 mm


# ---------------------------------------------------------------- Créneaux
def nb_creneaux(longueur):
    n = max(3, int(round(longueur / CRENEAU)))
    return n if n % 2 else n + 1


def panneau(lu, lv, bords):
    """Rectangle lu x lv dont chaque bord est 'A' (créneaux aux extrémités) ou 'B' (encoches aux extrémités).
    bords = dict(bas, haut, gauche, droite). Deux bords qui s'assemblent sont de types opposés."""
    forme = CrossSection.square((lu, lv))
    encoches = []
    for bord, type_ in bords.items():
        long = lu if bord in ("bas", "haut") else lv
        n = nb_creneaux(long)
        f = long / n
        for i in range(n):
            creux = (i % 2 == 1) if type_ == "A" else (i % 2 == 0)
            if not creux:
                continue
            if bord == "bas":
                encoches.append(CrossSection.square((f, T)).translate((i * f, 0)))
            elif bord == "haut":
                encoches.append(CrossSection.square((f, T)).translate((i * f, lv - T)))
            elif bord == "gauche":
                encoches.append(CrossSection.square((T, f)).translate((0, i * f)))
            else:
                encoches.append(CrossSection.square((T, f)).translate((lu - T, i * f)))
    for e in encoches:
        forme = forme - e
    return forme


def rect(u, v, w, h):
    return CrossSection.square((w, h)).translate((u, v))


def rond(u, v, r):
    return CrossSection.circle(r, 64).translate((u, v))


def percer(forme, trous):
    for t in trous:
        forme = forme - t
    return forme


# ---------------------------------------------------------------- Les six panneaux
def panneaux():
    p = {}
    # Avant / arrière : créneaux partout (type A)
    avant = panneau(W, H, dict(bas="A", haut="A", gauche="A", droite="A"))
    trous = [rect(OLED["u"], OLED["v"], OLED["w"], OLED["h"]), rond(PIR["u"], PIR["v"], PIR["r"])]
    trous += [rond(l["u"], l["v"], LED_R) for l in LEDS]
    trous += [rond(BUZZER["u"] + i * BUZZER["pas"], BUZZER["v"] + j * BUZZER["pas"], BUZZER["r"])
              for i in (-1, 0, 1) for j in (-1, 0, 1)]
    p["avant"] = (percer(avant, trous), W, H, [GRAVURE_AVANT])
    arriere = panneau(W, H, dict(bas="A", haut="A", gauche="A", droite="A"))
    p["arriere"] = (percer(arriere, [rond(CABLE["u"], CABLE["v"], CABLE["r"])]), W, H, [])
    # Côtés : verticaux en encoches (B), haut et bas en créneaux (A)
    cote = dict(bas="A", haut="A", gauche="B", droite="B")
    gauche = panneau(D, H, cote)
    fentes = [rect(DHT_FENTES["u0"] + k * DHT_FENTES["pas"], DHT_FENTES["v0"], DHT_FENTES["w"], DHT_FENTES["h"])
              for k in range(DHT_FENTES["n"])]
    p["gauche"] = (percer(gauche, fentes), D, H, [])
    droit = panneau(D, H, cote)
    p["droit"] = (percer(droit, [rect(USB["u"] - USB["w"] / 2, USB["v"] - USB["h"] / 2, USB["w"], USB["h"]),
                                 rect(CHARGE["u"] - CHARGE["w"] / 2, CHARGE["v"] - CHARGE["h"] / 2, CHARGE["w"], CHARGE["h"])]), D, H, [])
    # Dessus / fond : encoches partout (B) ; le dessus n'est pas collé, il s'emboîte et se retire
    dessus = panneau(W, D, dict(bas="B", haut="B", gauche="B", droite="B"))
    trous = []
    pas = MQ2["pas"]
    for i in range(-5, 6):
        for j in range(-5, 6):
            u = MQ2["u"] + i * pas + (j % 2) * pas / 2
            v = MQ2["v"] + j * pas * 0.866
            if (u - MQ2["u"]) ** 2 + (v - MQ2["v"]) ** 2 <= MQ2["r"] ** 2:
                trous.append(rond(u, v, MQ2["trou"]))
    a = AERATION
    trous += [rect(a["u0"] + k * a["pas"], a["v"] - a["l"] / 2, a["w"], a["l"]) for k in range(a["n"])]
    p["dessus"] = (percer(dessus, trous), W, D, GRAVURE_DESSUS)
    fond = panneau(W, D, dict(bas="B", haut="B", gauche="B", droite="B"))
    eu, ev = NODEMCU["ecart"]
    p["fond"] = (percer(fond, [rond(NODEMCU["u"] + su * eu / 2, NODEMCU["v"] + sv * ev / 2, NODEMCU["trou"])
                               for su in (-1, 1) for sv in (-1, 1)]), W, D, [])
    # Compensation du trait laser : la pièce grossit de KERF/2, les trous rétrécissent d'autant
    return {k: (f.offset(KERF / 2, JoinType.Miter), lu, lv, g) for k, (f, lu, lv, g) in p.items()}


# ---------------------------------------------------------------- Plan de découpe SVG
def svg(p, chemin):
    marge, ecart = 10.0, 6.0
    lignes = [["dessus", "fond"], ["avant", "arriere"], ["gauche", "droit"]]
    largeur = max(sum(p[k][1] for k in l) + ecart * (len(l) - 1) for l in lignes) + 2 * marge
    hauteur = sum(max(p[k][2] for k in l) for l in lignes) + ecart * (len(lignes) - 1) + 2 * marge
    morceaux = []
    y = marge
    for ligne in lignes:
        x = marge
        h_ligne = max(p[k][2] for k in ligne)
        for nom in ligne:
            forme, lu, lv, gravures = p[nom]
            d = ""
            for poly in forme.to_polygons():
                pts = " L ".join(f"{x + u:.3f},{y + lv - v:.3f}" for u, v in poly)
                d += f"M {pts} Z "
            morceaux.append(f'<path d="{d}" fill="none" stroke="#FF0000" stroke-width="0.1"/>')
            for g in gravures:
                morceaux.append(f'<text x="{x + g["u"]:.2f}" y="{y + lv - g["v"]:.2f}" font-family="Arial" '
                                f'font-weight="bold" font-size="{g["taille"]}" fill="#0000FF">{g["texte"]}</text>')
            x += lu + ecart
        y += h_ligne + ecart
    contenu = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{largeur:.1f}mm" height="{hauteur:.1f}mm" '
               f'viewBox="0 0 {largeur:.1f} {hauteur:.1f}">\n'
               f'<!-- Sentinel-X : boîtier bois {T:g} mm. Rouge = découpe, bleu = gravure. Échelle 1:1 en mm. -->\n'
               + "\n".join(morceaux) + "\n</svg>\n")
    open(chemin, "w", encoding="utf-8").write(contenu)
    return largeur, hauteur


# ---------------------------------------------------------------- Plans DXF sur planches A4
A4 = (297.0, 210.0)
MARGE_A4 = 5.0
PLANCHES = [["avant", "dessus"], ["arriere", "fond"], ["gauche", "droit"]]  # 2 panneaux par planche


def disposer(p, noms):
    """Place les panneaux d'une planche : empilés s'ils tiennent en hauteur, sinon côte à côte."""
    places, x, y = [], MARGE_A4, MARGE_A4
    hauteur = sum(p[n][2] for n in noms) + 6 * (len(noms) - 1)
    if hauteur <= A4[1] - 2 * MARGE_A4:
        for n in noms:
            places.append((n, MARGE_A4, y)); y += p[n][2] + 6
    else:
        for n in noms:
            places.append((n, x, MARGE_A4)); x += p[n][1] + 6
    for n, px, py in places:
        assert px + p[n][1] <= A4[0] - MARGE_A4 + 0.5 and py + p[n][2] <= A4[1] - MARGE_A4 + 0.5, f"{n} dépasse l'A4"
    return places


def dxf(p):
    import ezdxf
    fichiers = []
    for i, noms in enumerate(PLANCHES, 1):
        doc = ezdxf.new("R2010", setup=True)
        doc.header["$INSUNITS"] = 4  # millimètres
        doc.layers.add("DECOUPE", color=1)
        doc.layers.add("GRAVURE", color=5)
        msp = doc.modelspace()
        for n, px, py in disposer(p, noms):
            forme, lu, lv, gravures = p[n]
            for poly in forme.to_polygons():
                msp.add_lwpolyline([(px + u, py + v) for u, v in poly], close=True, dxfattribs={"layer": "DECOUPE"})
            for g in gravures:
                msp.add_text(g["texte"], height=g["taille"] * 0.72,
                             dxfattribs={"layer": "GRAVURE", "style": "OpenSans"}).set_placement((px + g["u"], py + g["v"] - g["taille"] * 0.25))
        chemin = os.path.join(HERE, f"decoupe_A4_{i}.dxf")
        doc.saveas(chemin)
        fichiers.append(chemin)
    return fichiers


def apercu_planches(p, chemin):
    from PIL import Image, ImageDraw, ImageFont
    k = 3.0  # pixels par mm
    lw, lh = int(A4[0] * k), int(A4[1] * k)
    img = Image.new("RGB", (lw * 3 + 80, lh + 90), (228, 230, 243))
    d = ImageDraw.Draw(img)
    try:
        f = ImageFont.truetype("arialbd.ttf", 26)
    except OSError:
        f = ImageFont.load_default()
    for i, noms in enumerate(PLANCHES):
        ox, oy = 20 + i * (lw + 20), 60
        d.rectangle([ox, oy, ox + lw, oy + lh], fill=(255, 255, 255), outline=(38, 30, 72), width=3)
        d.text((ox + lw / 2, 30), f"Planche A4 n° {i + 1} : " + " + ".join(noms), fill=(38, 30, 72), font=f, anchor="mm")
        for n, px, py in disposer(p, noms):
            forme = p[n][0]
            for poly in forme.to_polygons():
                pts = [(ox + (px + u) * k, oy + lh - (py + v) * k) for u, v in poly]
                d.line(pts + [pts[0]], fill=(220, 30, 30), width=2)
    img.save(chemin)


# ---------------------------------------------------------------- Montage 3D (pour les aperçus)
def volume(forme):
    return Manifold.extrude(forme, T)


def montage(p, ecarte=0.0):
    e = ecarte
    pieces = {
        "fond": volume(p["fond"][0]).translate((0, 0, -e)),
        "dessus": volume(p["dessus"][0]).translate((0, 0, H - T + e)),
        "avant": volume(p["avant"][0]).rotate((90, 0, 0)).translate((0, T - e, 0)),
        "arriere": volume(p["arriere"][0]).rotate((90, 0, 0)).translate((0, D + e, 0)),
        "gauche": volume(p["gauche"][0]).rotate((90, 0, 90)).translate((-e, 0, 0)),
        "droit": volume(p["droit"][0]).rotate((90, 0, 90)).translate((W - T + e, 0, 0)),
    }
    return pieces


def vers_trimesh(m):
    mesh = m.to_mesh()
    return trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts), process=True)


def _rgb(hexa):
    hexa = hexa.lstrip("#")
    return np.array([int(hexa[i:i + 2], 16) for i in (0, 2, 4)], float)


def apercu(pieces, chemin, titre, elev=22, azim=32, etiquettes=(), taille=(1600, 1100), ss=2):
    """Rendu ombré avec tampon de profondeur (z-buffer), contours des arêtes vives et étiquettes."""
    from PIL import Image, ImageDraw, ImageFont

    el, az = np.radians(elev), np.radians(azim)
    cam = np.array([np.cos(el) * np.sin(az), -np.cos(el) * np.cos(az), np.sin(el)])  # vers la caméra
    droite = np.cross([0, 0, 1], cam)
    droite /= np.linalg.norm(droite)
    haut = np.cross(cam, droite)
    vue = np.stack([droite, haut, cam])           # x écran, y écran, profondeur
    lum1 = vue.T @ np.array([-0.45, 0.6, 0.66])   # lumière principale (haut gauche, côté caméra)
    lum1 /= np.linalg.norm(lum1)

    Wpx, Hpx = taille[0] * ss, taille[1] * ss
    pts = np.vstack([m.vertices for m, _ in pieces]) @ vue.T
    lo, hi = pts[:, :2].min(axis=0), pts[:, :2].max(axis=0)
    marge_haut = 0.12
    echelle = min(Wpx * 0.78 / (hi[0] - lo[0]), Hpx * (0.80 - marge_haut) / (hi[1] - lo[1]))
    centre = (lo + hi) / 2
    ox, oy = Wpx / 2, Hpx * (0.5 + marge_haut / 2)

    def proj(p):
        q = p @ vue.T
        return np.stack([ox + (q[:, 0] - centre[0]) * echelle, oy - (q[:, 1] - centre[1]) * echelle, q[:, 2]], axis=1)

    fond = _rgb("#E4E6F3")
    img = np.tile(fond, (Hpx, Wpx, 1))
    zb = np.full((Hpx, Wpx), -np.inf)
    for mesh, couleur in pieces:
        base = _rgb(couleur)
        P = proj(mesh.vertices)
        n = mesh.face_normals
        visible = n @ cam > 1e-6
        lum = 0.42 + 0.58 * np.clip(n @ lum1, 0, 1) + 0.12 * np.clip(n @ cam, 0, 1)
        for f, k in zip(mesh.faces[visible], lum[visible]):
            t = P[f]
            x0, x1 = int(max(np.floor(t[:, 0].min()), 0)), int(min(np.ceil(t[:, 0].max()), Wpx - 1))
            y0, y1 = int(max(np.floor(t[:, 1].min()), 0)), int(min(np.ceil(t[:, 1].max()), Hpx - 1))
            if x1 < x0 or y1 < y0:
                continue
            xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            (ax_, ay, az_), (bx, by, bz), (cx, cy, cz) = t
            det = (by - cy) * (ax_ - cx) + (cx - bx) * (ay - cy)
            if abs(det) < 1e-9:
                continue
            w0 = ((by - cy) * (xs - cx) + (cx - bx) * (ys - cy)) / det
            w1 = ((cy - ay) * (xs - cx) + (ax_ - cx) * (ys - cy)) / det
            w2 = 1 - w0 - w1
            m = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
            if not m.any():
                continue
            z = w0 * az_ + w1 * bz + w2 * cz
            zone = zb[y0:y1 + 1, x0:x1 + 1]
            maj = m & (z > zone)
            zone[maj] = z[maj]
            img[y0:y1 + 1, x0:x1 + 1][maj] = np.clip(base * k, 0, 255)

        # Contours : arêtes entre faces formant un angle marqué
        aretes = mesh.face_adjacency_edges[mesh.face_adjacency_angles > np.radians(28)]
        if len(aretes):
            a, b = mesh.vertices[aretes[:, 0]], mesh.vertices[aretes[:, 1]]
            Pa, Pb = proj(a), proj(b)
            nb = np.maximum(2, np.ceil(np.linalg.norm(Pb[:, :2] - Pa[:, :2], axis=1)).astype(int) * 2)
            idx = np.repeat(np.arange(len(aretes)), nb)
            tt = np.concatenate([np.linspace(0, 1, k) for k in nb])
            S = Pa[idx] + (Pb[idx] - Pa[idx]) * tt[:, None]
            xi, yi = np.clip(S[:, 0].astype(int), 0, Wpx - 1), np.clip(S[:, 1].astype(int), 0, Hpx - 1)
            ok = S[:, 2] >= zb[yi, xi] - 0.6
            trait = np.clip(base * 0.35, 0, 255)
            for dx in (0, 1):
                for dy in (0, 1):
                    img[np.clip(yi[ok] + dy, 0, Hpx - 1), np.clip(xi[ok] + dx, 0, Wpx - 1)] = trait

    im = Image.fromarray(img.astype(np.uint8)).resize(taille, Image.LANCZOS)
    dessin = ImageDraw.Draw(im)

    def police(t, gras=False):
        for nom in (("arialbd.ttf", "DejaVuSans-Bold.ttf") if gras else ("arial.ttf", "DejaVuSans.ttf")):
            try:
                return ImageFont.truetype(nom, t)
            except OSError:
                pass
        return ImageFont.load_default()

    encre = (38, 30, 72)
    dessin.text((taille[0] / 2, 48), titre, fill=encre, font=police(44, True), anchor="mm")
    for (point, texte, (dx, dy)) in etiquettes:
        q = proj(np.array([point], float))[0] / ss
        tx, ty = q[0] + dx, q[1] + dy
        dessin.line([(q[0], q[1]), (tx, ty)], fill=(232, 116, 59), width=3)
        dessin.ellipse([q[0] - 6, q[1] - 6, q[0] + 6, q[1] + 6], fill=(232, 116, 59))
        f = police(26, True)
        boite_txt = dessin.textbbox((tx, ty), texte, font=f, anchor="lm" if dx >= 0 else "rm")
        dessin.rounded_rectangle([boite_txt[0] - 10, boite_txt[1] - 6, boite_txt[2] + 10, boite_txt[3] + 6], 8, fill=encre)
        dessin.text((tx, ty), texte, fill=(228, 230, 243), font=f, anchor="lm" if dx >= 0 else "rm")
    im.save(chemin)



def main():
    p = panneaux()
    largeur, hauteur = svg(p, os.path.join(HERE, "decoupe_laser_3mm.svg"))
    print(f"plan de découpe : {largeur:.0f} x {hauteur:.0f} mm (plaque de bois {T:g} mm)")
    for f in dxf(p):
        print("DXF A4 :", os.path.basename(f))
    apercu_planches(p, os.path.join(HERE, "decoupe_A4.png"))

    # Contrôle : les six panneaux montés ne doivent jamais se chevaucher
    pieces = montage(p)
    noms = list(pieces)
    pire = 0.0
    for i in range(len(noms)):
        for j in range(i + 1, len(noms)):
            pire = max(pire, (pieces[noms[i]] ^ pieces[noms[j]]).volume())
    print(f"chevauchement maximal entre deux panneaux : {pire:.2f} mm3 (dû au seul jeu de découpe {KERF} mm)")

    bois, bois_fonce = "#C9A27E", "#B08560"
    couleur = dict(fond=bois_fonce, dessus=bois, avant=bois, arriere=bois_fonce, gauche=bois_fonce, droit=bois)
    meshes = [(vers_trimesh(m), couleur[k]) for k, m in pieces.items()]
    etiquettes = [
        ((OLED["u"] + OLED["w"] / 2, 0, OLED["v"] + OLED["h"] / 2), "Écran OLED", (-140, -150)),
        ((PIR["u"], 0, PIR["v"]), "Dôme du PIR", (-200, 170)),
        ((LEDS[0]["u"], 0, LEDS[0]["v"]), "LEDs rouge / verte", (-40, -200)),
        ((BUZZER["u"], 0, BUZZER["v"]), "Buzzer", (-30, 170)),
        ((MQ2["u"], MQ2["v"], H), "Grille du MQ-2", (-220, -110)),
        ((AERATION["u0"] + 20, AERATION["v"], H), "Aération", (80, -150)),
        ((W, USB["u"], USB["v"]), "USB (programmation)", (150, 145)),
        ((W, CHARGE["u"], CHARGE["v"]), "Recharge batterie", (120, 55)),
    ]
    apercu(meshes, os.path.join(HERE, "apercu_assemble.png"),
           f"Sentinel-X : boîtier bois {T:g} mm ({W:g} x {D:g} x {H:g} mm)", etiquettes=etiquettes)
    eclate = montage(p, ecarte=28)
    apercu([(vers_trimesh(m), couleur[k]) for k, m in eclate.items()], os.path.join(HERE, "apercu_eclate.png"),
           "Sentinel-X : montage par créneaux, sans colle ni vis", elev=26, azim=-35,
           etiquettes=[((-28, DHT_FENTES["u0"] + 15, DHT_FENTES["v0"] + 13), "Fentes du DHT22", (-40, 190))])
    print("fichiers générés dans", HERE)


if __name__ == "__main__":
    main()
