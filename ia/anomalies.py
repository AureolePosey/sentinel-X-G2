"""
Sentinel-X : maintenance prédictive (filière IA).

Principe : pas de seuil fixe du type "if temp > 40". Un modèle Isolation Forest (scikit-learn) apprend
à quoi ressemble le fonctionnement NORMAL du boîtier, puis signale ce qui s'en écarte.

Chaque point analysé décrit une fenêtre glissante de 30 s de télémétrie (15 mesures) :
  température, humidité, gaz            -> le niveau
  pente de température (°C/min)         -> une hausse lente, invisible sur une seule mesure
  pente du gaz (unités/min), écart-type -> une micro-dérive du gaz, bien avant le seuil d'alerte critique
  pente d'humidité (%/min)
C'est la COMBINAISON inhabituelle de ces valeurs (ex. température qui monte doucement + gaz qui dérive)
que l'Isolation Forest isole, avant que l'alerte statique de l'API (gaz >= seuil) ne se déclenche.

Lancement : python anomalies.py          (lit la télémétrie via GET /api/v1/telemetry)
Auto-test : python anomalies.py --test   (données synthétiques, sans serveur : pour comprendre et démontrer)
"""
import sys
import time
from datetime import datetime

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from common import get_json, load_env, send_alert, setting

WINDOW = 15                 # mesures par fenêtre (15 x 2 s = 30 s)
MIN_TRAIN = 150             # fenêtres minimum avant d'entraîner (~5 min de données : moins de fausses alertes)
RETRAIN_EVERY = 600         # réentraînement toutes les 10 min sur les données jugées normales
FEATURES = ["temp", "hum", "gaz", "pente temp (°C/min)", "pente gaz (/min)", "variation gaz", "pente hum (%/min)"]


# ---------------------------------------------------------------- Caractéristiques
def slope_per_min(t_sec, values):
    """Pente d'une droite ajustée sur la fenêtre (régression linéaire), en unités par minute."""
    t = t_sec - t_sec[0]
    if t[-1] <= 0:
        return 0.0
    return float(np.polyfit(t, values, 1)[0] * 60)


def window_features(rows):
    """rows : liste de mesures {ts, temp, hum, gas} -> une ligne de caractéristiques par fenêtre."""
    t = np.array([r["t"] for r in rows], float)
    temp = np.array([r["temp"] for r in rows], float)
    hum = np.array([r["hum"] for r in rows], float)
    gas = np.array([r["gas"] for r in rows], float)
    out, ends = [], []
    for end in range(WINDOW, len(rows) + 1):
        s = slice(end - WINDOW, end)
        if np.isnan(temp[s]).any() or np.isnan(hum[s]).any():
            continue
        if t[s][-1] - t[s][0] > WINDOW * 2 * 3:  # trou dans les données (boîtier hors ligne) : fenêtre ignorée
            continue
        out.append([temp[s][-1], hum[s][-1], gas[s][-1],
                    slope_per_min(t[s], temp[s]), slope_per_min(t[s], gas[s]),
                    float(np.std(gas[s])), slope_per_min(t[s], hum[s])])
        ends.append(end - 1)
    return np.array(out), ends


def parse_telemetry(items):
    rows = []
    for it in items:
        try:
            ts = datetime.fromisoformat(it["ts"].replace("Z", "+00:00")).timestamp()
        except (KeyError, ValueError, AttributeError):
            continue
        rows.append({"t": ts,
                     "temp": np.nan if it.get("temp") is None else it["temp"],
                     "hum": np.nan if it.get("hum") is None else it["hum"],
                     "gas": it.get("gas", 0)})
    rows.sort(key=lambda r: r["t"])
    return rows


# ---------------------------------------------------------------- Modèle
class AnomalyModel:
    def __init__(self):
        self.scaler = StandardScaler()
        self.forest = IsolationForest(n_estimators=200, contamination=0.02, random_state=42)
        self.trained_at = 0.0
        self.mean = self.std = None

    def fit(self, X):
        Xs = self.scaler.fit_transform(X)
        self.forest.fit(Xs)
        self.mean, self.std = X.mean(axis=0), X.std(axis=0) + 1e-6
        self.trained_at = time.time()

    def score(self, X):
        """Renvoie (est_anormal[], score[]) ; score < 0 = anormal, plus c'est bas plus c'est étrange."""
        Xs = self.scaler.transform(X)
        return self.forest.predict(Xs) == -1, self.forest.decision_function(Xs)

    def explain(self, x):
        """Les 2 caractéristiques les plus éloignées de l'habitude (en écarts-types) : pour un message lisible."""
        z = (x - self.mean) / self.std
        top = np.argsort(-np.abs(z))[:2]
        return [(FEATURES[i], float(x[i]), float(z[i])) for i in top]


def describe(explanation):
    return ", ".join(f"{name} = {value:.2f} ({z:+.1f} σ)" for name, value, z in explanation)


# ---------------------------------------------------------------- Boucle temps réel
def run():
    load_env()
    poll = float(setting("POLL_SECONDS", "5"))
    model = AnomalyModel()
    abnormal_streak, normal_streak, alerted = 0, 0, False
    print(f"[anomalies] lecture de {setting('API_URL', 'http://localhost:3000')}/api/v1/telemetry toutes les {poll:.0f} s")

    while True:
        try:
            rows = parse_telemetry(get_json("/api/v1/telemetry?limit=1000"))
        except OSError as e:
            print(f"[anomalies] API injoignable : {e}")
            time.sleep(poll)
            continue

        X, _ = window_features(rows)
        if len(X) < MIN_TRAIN:
            print(f"[anomalies] apprentissage en attente : {len(X)}/{MIN_TRAIN} fenêtres de données")
            time.sleep(poll)
            continue

        if model.trained_at == 0 or time.time() - model.trained_at > RETRAIN_EVERY:
            if model.trained_at:
                # On réapprend seulement sur ce que le modèle actuel juge normal (sinon il "apprend" la panne)
                flags, _ = model.score(X)
                X = X[~flags] if (~flags).sum() >= MIN_TRAIN else X
            model.fit(X)
            print(f"[anomalies] modèle entraîné sur {len(X)} fenêtres")

        latest, _ = window_features(rows[-WINDOW:])
        if not len(latest):
            time.sleep(poll)
            continue
        flags, scores = model.score(latest)
        x, score = latest[-1], float(scores[-1])

        # Une anomalie doit être confirmée 2 fois de suite (10 s) pour éviter les fausses alertes
        abnormal_streak = abnormal_streak + 1 if flags[-1] else 0
        normal_streak = 0 if flags[-1] else normal_streak + 1
        if abnormal_streak >= 2 and not alerted:
            alerted = True
            why = describe(model.explain(x))
            send_alert("ia-anomaly", "anomaly", "warning",
                       f"Comportement anormal du boîtier (score {score:.3f}) : {why}",
                       {"score": round(score, 4), **{n: round(float(v), 3) for n, v in zip(FEATURES, x)}})
        elif alerted and normal_streak >= 6:
            alerted = False
            send_alert("ia-anomaly", "state_change", "info", "Modèle d'anomalies : retour à un comportement normal", {})

        print(f"[anomalies] score {score:+.3f} {'ANORMAL' if flags[-1] else 'normal'} | {describe(model.explain(x))}")
        time.sleep(poll)


# ---------------------------------------------------------------- Auto-test (sans serveur)
def synthetic(minutes, temp_slope=0.0, gas_slope=0.0, seed=0):
    """Série de mesures toutes les 2 s : bruit réaliste + éventuelle dérive lente (par minute)."""
    rng = np.random.default_rng(seed)
    n = int(minutes * 30)
    t = np.arange(n) * 2.0
    temp = 22 + 0.15 * np.sin(t / 300) + rng.normal(0, 0.05, n) + temp_slope * t / 60
    hum = 50 + rng.normal(0, 0.3, n)
    gas = 150 + rng.normal(0, 3, n) + gas_slope * t / 60
    return [{"t": float(a), "temp": float(b), "hum": float(c), "gas": float(d)} for a, b, c, d in zip(t, temp, hum, gas)]


def self_test():
    print("Apprentissage sur 30 minutes de fonctionnement normal (synthétique)...")
    model = AnomalyModel()
    X, _ = window_features(synthetic(30, seed=1))
    model.fit(X)
    cases = [
        ("normal", synthetic(2, seed=2)),
        ("hausse lente de température (+0,6 °C/min) + micro-dérive du gaz (+8/min)", synthetic(2, 0.6, 8, seed=3)),
        ("hausse lente de température seule (+0,6 °C/min)", synthetic(2, 0.6, 0, seed=4)),
    ]
    for name, rows in cases:
        Xc, _ = window_features(rows)
        flags, scores = model.score(Xc)
        last = rows[-1]
        print(f"\n- {name}")
        print(f"  fin de série : temp {last['temp']:.1f} °C, gaz {last['gas']:.0f} (seuil statique de l'API : 400)")
        print(f"  fenêtres jugées anormales : {flags.mean():.0%}, score moyen {scores.mean():+.3f}")
        if flags.any():
            print(f"  pourquoi : {describe(model.explain(Xc[np.argmin(scores)]))}")


if __name__ == "__main__":
    try:
        self_test() if "--test" in sys.argv else run()
    except KeyboardInterrupt:
        print("Arrêt.")
