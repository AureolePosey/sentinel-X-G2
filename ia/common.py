"""Outils partagés par vision.py et anomalies.py : configuration (.env) et envoi d'alertes à l'API."""
import json
import os
import threading
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def load_env(path=os.path.join(HERE, ".env")):
    """Lit ia/.env (CLE=valeur). Les variables d'environnement déjà définies restent prioritaires."""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())


def setting(name, default=""):
    return os.environ.get(name, default) or default


def api_url(path):
    return setting("API_URL", "http://localhost:3000").rstrip("/") + path


def get_json(path, timeout=3):
    with urllib.request.urlopen(api_url(path), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def send_alert(source, type_, level, message, data=None):
    """POST /api/v1/alerts dans un thread : la vidéo ou l'analyse ne sont jamais bloquées par le réseau."""
    if not setting("API_KEY"):
        # Sans clé, chaque essai serait refusé (401) et compterait dans l'anti force brute de l'API
        print(f"[alerte] non envoyée (API_KEY vide dans ia/.env) : {message}")
        return

    def post():
        body = json.dumps({"source": source, "type": type_, "level": level,
                           "message": message[:300], "data": data or {}}).encode("utf-8")
        req = urllib.request.Request(api_url("/api/v1/alerts"), data=body, method="POST", headers={
            "Content-Type": "application/json", "X-API-Key": setting("API_KEY")})
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                print(f"[alerte] envoyée ({r.status}) : {message}")
        except urllib.error.HTTPError as e:
            print(f"[alerte] refusée par l'API ({e.code}) : {e.read().decode('utf-8', 'replace')[:200]}")
        except OSError as e:
            print(f"[alerte] API injoignable : {e}")

    threading.Thread(target=post, daemon=True).start()
