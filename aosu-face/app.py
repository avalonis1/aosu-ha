"""Lightweight single-container InsightFace recognition server for Aosu Cameras.

Exposes a CompreFace-compatible endpoint (`POST /api/v1/recognition/recognize`)
plus a minimal French Web UI on `/` to manage family faces without Java or PostgreSQL.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

DATA_DIR = Path(os.environ.get("AOSU_FACE_DATA_DIR", "/data"))
FACES_DIR = DATA_DIR / "faces"
INDEX_FILE = DATA_DIR / "faces_index.json"
MODEL_NAME = os.environ.get("AOSU_FACE_MODEL", "buffalo_sc")
API_KEY = os.environ.get("AOSU_FACE_API_KEY", "aosu-local-key").strip()
DEFAULT_THRESHOLD = float(os.environ.get("AOSU_FACE_THRESHOLD", "0.45"))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def sanitize_subject_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9À-ÿ _-]", "", name).strip()
    if not cleaned:
        raise ValueError("Nom de personne invalide.")
    return cleaned


class FaceEngine:
    """Lazy-loaded InsightFace CPU engine with persistent JSON embedding index."""

    def __init__(self, faces_dir: Path = FACES_DIR, index_file: Path = INDEX_FILE) -> None:
        self.faces_dir = faces_dir
        self.index_file = index_file
        self.embeddings: dict[str, list[list[float]]] = {}
        self._app: Any = None
        self._load_index()

    def _load_index(self) -> None:
        if self.index_file.exists():
            try:
                self.embeddings = json.loads(self.index_file.read_text(encoding="utf-8"))
            except Exception:
                self.embeddings = {}

    def _save_index(self) -> None:
        self.index_file.parent.mkdir(parents=True, exist_ok=True)
        self.index_file.write_text(json.dumps(self.embeddings), encoding="utf-8")

    def _ensure_model(self) -> Any:
        if self._app is not None:
            return self._app
        import insightface  # type: ignore[import-not-found]

        app = insightface.app.FaceAnalysis(
            name=MODEL_NAME,
            providers=["CPUExecutionProvider"],
        )
        app.prepare(ctx_id=-1, det_size=(640, 640))
        self._app = app
        return app

    def extract_faces(self, image_bytes: bytes) -> list[dict[str, Any]]:
        import cv2  # type: ignore[import-not-found]
        import numpy as np  # type: ignore[import-not-found]

        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Image JPEG/PNG invalide.")
        faces = self._ensure_model().get(img)
        results: list[dict[str, Any]] = []
        for f in faces:
            x1, y1, x2, y2 = [float(v) for v in f.bbox.tolist()]
            results.append(
                {
                    "box": {
                        "x_min": int(x1),
                        "y_min": int(y1),
                        "x_max": int(x2),
                        "y_max": int(y2),
                    },
                    "embedding": f.normed_embedding.tolist(),
                }
            )
        return results

    def add_subject_photo(self, name: str, image_bytes: bytes, ext: str = ".jpg") -> int:
        safe_name = sanitize_subject_name(name)
        faces = self.extract_faces(image_bytes)
        if not faces:
            raise ValueError("Aucun visage détecté sur cette photo.")
        best = max(
            faces,
            key=lambda f: (f["box"]["x_max"] - f["box"]["x_min"])
            * (f["box"]["y_max"] - f["box"]["y_min"]),
        )
        person_dir = self.faces_dir / safe_name
        person_dir.mkdir(parents=True, exist_ok=True)
        (person_dir / f"{uuid.uuid4().hex[:10]}{ext}").write_bytes(image_bytes)
        self.embeddings.setdefault(safe_name, []).append(best["embedding"])
        self._save_index()
        return len(self.embeddings[safe_name])

    def delete_subject(self, name: str) -> None:
        safe_name = sanitize_subject_name(name)
        self.embeddings.pop(safe_name, None)
        person_dir = self.faces_dir / safe_name
        if person_dir.exists() and person_dir.is_dir():
            shutil.rmtree(person_dir)
        self._save_index()

    def recognize(self, image_bytes: bytes) -> list[dict[str, Any]]:
        faces = self.extract_faces(image_bytes)
        output: list[dict[str, Any]] = []
        for face in faces:
            emb = face["embedding"]
            scored: list[tuple[str, float]] = []
            for subject, vecs in self.embeddings.items():
                best_for_subject = max(
                    (cosine_similarity(emb, v) for v in vecs),
                    default=0.0,
                )
                # Map cosine [-1..1] to [0..1] similarity compatible with CompreFace thresholds
                norm_sim = max(0.0, min(1.0, (best_for_subject + 1.0) / 2.0))
                scored.append((subject, round(norm_sim, 4)))
            scored.sort(key=lambda x: x[1], reverse=True)
            subjects_payload = [
                {"subject": s, "similarity": sim} for s, sim in scored[:3]
            ]
            output.append({"box": face["box"], "subjects": subjects_payload})
        return output

    def list_subjects(self) -> dict[str, int]:
        return {name: len(vecs) for name, vecs in sorted(self.embeddings.items())}


engine = FaceEngine()
app = FastAPI(title="Aosu Face (InsightFace Local)", version="0.1.0")


def _check_api_key(x_api_key: str | None) -> None:
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Clé API invalide (x-api-key)")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "subjects": engine.list_subjects(),
    }


@app.post("/api/v1/recognition/recognize")
async def recognize_endpoint(
    file: UploadFile = File(...),
    x_api_key: str | None = Header(default=None),
) -> JSONResponse:
    """CompreFace-compatible face recognition endpoint."""
    _check_api_key(x_api_key)
    image_bytes = await file.read()
    try:
        result = engine.recognize(image_bytes)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    if not result:
        return JSONResponse(status_code=400, content={"message": "No face is found in the given image"})
    return JSONResponse(content={"result": result})


@app.get("/api/subjects")
def api_list_subjects() -> dict[str, int]:
    return engine.list_subjects()


@app.post("/api/subjects")
async def api_add_subject(
    name: str = Form(...),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    image_bytes = await file.read()
    ext = Path(file.filename or "photo.jpg").suffix.lower() or ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        ext = ".jpg"
    try:
        count = engine.add_subject_photo(name, image_bytes, ext=ext)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {"name": sanitize_subject_name(name), "photos": count}


@app.delete("/api/subjects/{name}")
def api_delete_subject(name: str) -> dict[str, str]:
    try:
        engine.delete_subject(name)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {"deleted": name}


@app.get("/", response_class=HTMLResponse)
def web_ui() -> str:
    subjects = engine.list_subjects()
    rows = "".join(
        f"<li><b>{name}</b> ({cnt} photo(s)) "
        f"<button onclick=\"delSubject('{name}')\">Supprimer</button></li>"
        for name, cnt in subjects.items()
    ) or "<li><i>Aucun visage enregistré pour le moment.</i></li>"

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Aosu Face — Reconnaissance Faciale Locale</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; background: #111; color: #eee; }}
    .card {{ background: #1c1c1e; border-radius: 12px; padding: 1.25rem; margin-bottom: 1.25rem; }}
    input, button {{ padding: 0.5rem 0.75rem; border-radius: 8px; border: 1px solid #444; background: #2c2c2e; color: #fff; margin: 0.25rem 0; }}
    button {{ cursor: pointer; background: #0a84ff; border: none; }}
    button:hover {{ opacity: 0.9; }}
    pre {{ background: #000; padding: 0.75rem; border-radius: 8px; overflow-x: auto; }}
  </style>
</head>
<body>
  <h1>Aosu Face (Local)</h1>
  <div class="card">
    <h2>1. Visages enregistrés</h2>
    <ul>{rows}</ul>
  </div>
  <div class="card">
    <h2>2. Ajouter une photo de référence</h2>
    <form id="addForm">
      <input type="text" name="name" placeholder="Prénom (ex: Jérôme)" required><br>
      <input type="file" name="file" accept="image/*" required><br>
      <button type="submit">Ajouter le visage</button>
    </form>
    <div id="addMsg"></div>
  </div>
  <div class="card">
    <h2>3. Tester une photo</h2>
    <form id="testForm">
      <input type="file" name="file" accept="image/*" required><br>
      <button type="submit">Tester la reconnaissance</button>
    </form>
    <pre id="testOut">En attente...</pre>
  </div>
  <script>
    const API_KEY = "{API_KEY}";
    document.getElementById('addForm').onsubmit = async (e) => {{
      e.preventDefault();
      const fd = new FormData(e.target);
      const r = await fetch('/api/subjects', {{ method: 'POST', body: fd }});
      const j = await r.json();
      document.getElementById('addMsg').textContent = r.ok ? 'Ajouté : ' + JSON.stringify(j) : 'Erreur : ' + (j.detail || r.status);
      if (r.ok) setTimeout(() => location.reload(), 600);
    }};
    document.getElementById('testForm').onsubmit = async (e) => {{
      e.preventDefault();
      const fd = new FormData(e.target);
      const r = await fetch('/api/v1/recognition/recognize', {{ method: 'POST', headers: {{ 'x-api-key': API_KEY }}, body: fd }});
      document.getElementById('testOut').textContent = JSON.stringify(await r.json(), null, 2);
    }};
    async function delSubject(name) {{
      if (!confirm('Supprimer ' + name + ' ?')) return;
      await fetch('/api/subjects/' + encodeURIComponent(name), {{ method: 'DELETE' }});
      location.reload();
    }}
  </script>
</body>
</html>"""
