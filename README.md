# X-Mas Robo

Ein Tanzvideo oder die Webcam rein, ein Unitree G1 tanzt die Bewegung auf einer Winterbühne nach.
Die Wiedergabe ist kinematisch (keine Physik, kein Gleichgewicht).

## Browser-Version (`web/`)

Statische Seite, alles läuft im Browser: Pose-Erkennung mit MediaPipe, Übertragung auf die 29 Gelenke
des G1 in JavaScript, 3D-Bühne mit three.js. Das Video verlässt das Gerät nicht.

Lokal starten (aus dem Projektordner):

```bash
python -m http.server 5173
```

Dann `http://localhost:5173/web/` öffnen. Für Vercel ist `web/` das Ausgabeverzeichnis (`vercel.json`).

Test des Retargetings gegen die Python-Fassung:

```bash
node web/test/retarget.test.mjs
```

## Lokale App (Python)

Nimmt zusätzlich Links (TikTok, YouTube, ...) und rendert ein Vergleichsvideo mit Ton.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python server.py
```

Dann `http://localhost:8765` öffnen. Das Pose-Modell `pose_landmarker_heavy.task` von MediaPipe muss
in `models/` liegen. Ohne Oberfläche: `.venv/Scripts/python dance.py <Link oder Datei>`.

## Aufbau

| Ordner | Inhalt |
| --- | --- |
| `web/` | Browser-Version: `src/retarget.js` (Übertragung), `src/stage.js` (3D-Bühne), `src/pose.js` (Pose) |
| `app/` | Python-Pipeline: Download, Pose, Retargeting, Vergleichsvideo |
| `sim/` | MuJoCo-Szene (`build_xmas_scene.py` erzeugt sie), Player, G1-Modell |
| `tools/export_web.py` | exportiert Szene, Roboter und Demo-Tänze aus MuJoCo nach `web/assets/` |
| `ui/`, `server.py` | Oberfläche und Server der lokalen App |

Nach Änderungen an der Szene:

```bash
.venv/Scripts/python sim/build_xmas_scene.py
```

```bash
.venv/Scripts/python tools/export_web.py
```

## Quellen

- Robotermodell Unitree G1 aus [MuJoCo Menagerie](https://github.com/google-deepmind/mujoco_menagerie) (BSD-3-Clause, siehe `sim/g1/LICENSE`)
- Pose-Erkennung: MediaPipe Pose Landmarker
- Demo „Kathak": Bewegung abgeleitet aus einem Video von Wikimedia Commons
  (Vishvadeep performing Kathak at Khajuraho Dance Festival 2026)
