"""
Sentinel-X : vision intelligente (filière IA).

- capte la webcam USB du serveur, redimensionne chaque image en 640x480 ;
- détecte les personnes avec YOLOv8n (format ONNX, exécuté par OpenCV, sans GPU) ;
- dessine les cadres + le temps de traitement, et diffuse la vidéo en MJPEG sur http://<serveur>:5000/video ;
- envoie une alerte "human_detected" à l'API quand une personne APPARAÎT (pas à chaque image).

Lancement : python vision.py      (configuration dans ia/.env, voir .env.example)
"""
import collections
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

from common import HERE, load_env, send_alert, setting

FRAME_W, FRAME_H = 640, 480   # bridage systématique de la taille des images
PERSON = 0                    # classe "person" du jeu de données COCO


# ---------------------------------------------------------------- Détection
class YoloDetector:
    """YOLOv8n ONNX : une passe du réseau renvoie 8400 propositions (cx, cy, w, h + 80 scores de classes)."""

    def __init__(self, path, confidence):
        self.net = cv2.dnn.readNetFromONNX(path)
        self.size = 320 if "320" in os.path.basename(path) else 640  # taille d'entrée du modèle exporté
        self.confidence = confidence
        self.name = f"YOLOv8n {self.size}px"

    def detect(self, frame):
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (self.size, self.size), swapRB=True, crop=False)
        self.net.setInput(blob)
        out = self.net.forward()[0].T                 # (8400, 84)
        scores = out[:, 4 + PERSON]
        keep = scores >= self.confidence
        out, scores = out[keep], scores[keep]
        sx, sy = w / self.size, h / self.size
        boxes = [[int((cx - bw / 2) * sx), int((cy - bh / 2) * sy), int(bw * sx), int(bh * sy)]
                 for cx, cy, bw, bh in out[:, :4]]
        idx = cv2.dnn.NMSBoxes(boxes, scores.tolist(), self.confidence, 0.45)  # supprime les doublons
        return [(boxes[i], float(scores[i])) for i in np.array(idx).flatten()]


class HogDetector:
    """Secours si le fichier ONNX est absent : détecteur de silhouettes intégré à OpenCV (moins précis)."""

    def __init__(self):
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        self.name = "OpenCV HOG (secours)"

    def detect(self, frame):
        rects, weights = self.hog.detectMultiScale(frame, winStride=(8, 8), scale=1.1)
        return [(list(map(int, r)), float(min(1.0, wt / 2))) for r, wt in zip(rects, np.ravel(weights)) if wt > 0.5]


# ---------------------------------------------------------------- Caméra (thread dédié)
class Camera:
    """Lit la webcam en continu et ne garde que la DERNIÈRE image : pas de retard qui s'accumule."""

    def __init__(self, index):
        self.index = index
        self.frame = None
        self.count = 0  # numéro de la dernière image reçue
        self.lock = threading.Lock()
        threading.Thread(target=self._run, daemon=True).start()

    def _open(self):
        api = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
        cap = cv2.VideoCapture(self.index, api)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_W)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_H)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _run(self):
        while True:
            cap = self._open()
            if not cap.isOpened():
                print(f"[camera] webcam {self.index} introuvable, nouvel essai dans 3 s")
                time.sleep(3)
                continue
            print(f"[camera] webcam {self.index} ouverte")
            while True:
                ok, frame = cap.read()
                if not ok:
                    print("[camera] image perdue, reconnexion")
                    break
                with self.lock:
                    self.frame = frame
                    self.count += 1
            cap.release()
            with self.lock:
                self.frame = None
            time.sleep(1)

    def read(self):
        """Renvoie (numéro, image) ; image = None si la webcam est indisponible."""
        with self.lock:
            return self.count, None if self.frame is None else self.frame.copy()


# ---------------------------------------------------------------- Flux MJPEG (port 5000)
latest_jpeg = None
jpeg_lock = threading.Condition()


def publish(frame):
    global latest_jpeg
    ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    if ok:
        with jpeg_lock:
            latest_jpeg = jpg.tobytes()
            jpeg_lock.notify_all()


class MjpegHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] != "/video":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while True:
                with jpeg_lock:
                    jpeg_lock.wait(timeout=2)
                    img = latest_jpeg
                if img:
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                     + str(len(img)).encode() + b"\r\n\r\n" + img + b"\r\n")
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # le navigateur a fermé l'onglet

    def log_message(self, *args):
        pass  # pas une ligne de journal par image


def start_video_server(port):
    server = ThreadingHTTPServer(("0.0.0.0", port), MjpegHandler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[video] flux MJPEG sur http://<ip-du-serveur>:{port}/video")


# ---------------------------------------------------------------- Dessin
def draw(frame, detections, ms, fps, model_name, alarm):
    for (x, y, w, h), conf in detections:
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
        cv2.putText(frame, f"personne {conf:.0%}", (x, max(15, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
    color = (0, 0, 255) if alarm else (0, 200, 0)
    cv2.rectangle(frame, (0, 0), (FRAME_W, 26), (20, 20, 20), -1)
    cv2.putText(frame, f"{model_name} | {ms:.0f} ms/image | {fps:.0f} FPS | personnes : {len(detections)}",
                (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    if alarm:
        cv2.putText(frame, "PRESENCE HUMAINE", (8, FRAME_H - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)


def placeholder(text):
    img = np.zeros((FRAME_H, FRAME_W, 3), np.uint8)
    cv2.putText(img, text, (40, FRAME_H // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
    return img


# ---------------------------------------------------------------- Programme
def main():
    load_env()
    model_path = os.path.join(HERE, setting("MODEL", "models/yolov8n-320.onnx"))
    confidence = float(setting("CONFIDENCE", "0.5"))
    detector = YoloDetector(model_path, confidence) if os.path.exists(model_path) else HogDetector()
    if isinstance(detector, HogDetector):
        print(f"[vision] {model_path} absent : détecteur de secours HOG")
    print(f"[vision] modèle : {detector.name}")

    start_video_server(int(setting("VIDEO_PORT", "5000")))
    camera = Camera(int(setting("CAMERA", "0")))

    history = collections.deque(maxlen=5)  # présence sur les 5 dernières images (anti faux positif isolé)
    present, last_seen, last_alert = False, 0.0, 0.0
    fps, t_prev, last_log, last_count = 0.0, time.time(), 0.0, -1

    while True:
        count, frame = camera.read()
        if frame is None:
            publish(placeholder("Camera indisponible"))
            time.sleep(0.5)
            continue
        if count == last_count:  # pas encore de nouvelle image : on ne retraite pas la même
            time.sleep(0.005)
            continue
        last_count = count

        t0 = time.perf_counter()
        frame = cv2.resize(frame, (FRAME_W, FRAME_H))
        detections = detector.detect(frame)
        ms = (time.perf_counter() - t0) * 1000

        now = time.time()
        fps = 0.9 * fps + 0.1 * (1 / max(now - t_prev, 1e-3))
        t_prev = now

        # Présence confirmée si une personne est vue sur 3 des 5 dernières images
        history.append(bool(detections))
        if detections:
            last_seen = now
        if not present and sum(history) >= 3:
            present = True
            best = max(c for _, c in detections) if detections else 0
            if now - last_alert > 10:  # au plus une alerte toutes les 10 s
                last_alert = now
                send_alert("ia-vision", "human_detected", "critical",
                           f"Présence humaine détectée par la caméra ({len(detections)} pers., confiance {best:.2f})",
                           {"confidence": round(best, 2), "count": len(detections), "model": detector.name})
        elif present and now - last_seen > 5:  # plus personne depuis 5 s
            present = False
            send_alert("ia-vision", "state_change", "info", "Caméra : plus de présence humaine", {})

        draw(frame, detections, ms, fps, detector.name, present)
        publish(frame)

        if now - last_log > 10:
            last_log = now
            print(f"[vision] {ms:.0f} ms/image, {fps:.1f} FPS, {len(detections)} personne(s)")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Arrêt.")
