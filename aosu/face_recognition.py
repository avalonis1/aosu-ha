"""Local facial recognition engine for Aosu camera snapshots.

Supports two 100% local backends (no cloud, no paid subscription):
1. InsightFace (ONNX CPU, pure local Python): compares 512-D embeddings against
   reference photos placed in `faces/<person_name>/*.jpg`.
2. CompreFace (optional local Docker container): sends the snapshot JPEG to a
   local CompreFace REST endpoint (http://<host>:8000/api/v1/recognition/recognize).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx


@dataclass
class FaceMatch:
    name: str
    confidence: float
    bbox: list[float] = field(default_factory=list)
    is_known: bool = True


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two embedding vectors."""
    if not a or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class LocalEmbeddingMatcher:
    """Pure-Python embedding matcher (used by InsightFace backend & tests)."""

    def __init__(self, threshold: float = 0.45) -> None:
        self.threshold = threshold
        self.known_embeddings: dict[str, list[list[float]]] = {}

    def add_embedding(self, name: str, embedding: list[float]) -> None:
        self.known_embeddings.setdefault(name, []).append(embedding)

    def match(self, embedding: list[float], bbox: list[float] | None = None) -> FaceMatch:
        best_name = "Inconnu"
        best_score = 0.0
        for name, vectors in self.known_embeddings.items():
            for vec in vectors:
                score = cosine_similarity(embedding, vec)
                if score > best_score:
                    best_score = score
                    best_name = name
        if best_score >= self.threshold:
            return FaceMatch(name=best_name, confidence=round(best_score, 4), bbox=bbox or [], is_known=True)
        return FaceMatch(name="Inconnu", confidence=round(best_score, 4), bbox=bbox or [], is_known=False)

    def save_index(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.known_embeddings), encoding="utf-8")

    def load_index(self, path: str | Path) -> None:
        p = Path(path)
        if p.exists():
            self.known_embeddings = json.loads(p.read_text(encoding="utf-8"))


class InsightFaceRecognizer:
    """100% local CPU facial recognition using InsightFace (ONNX Runtime)."""

    def __init__(
        self,
        faces_dir: str | Path = "faces",
        index_file: str | Path = "faces_index.json",
        model_name: str = "buffalo_sc",
        threshold: float = 0.45,
    ) -> None:
        self.faces_dir = Path(faces_dir)
        self.index_file = Path(index_file)
        self.model_name = model_name
        self.matcher = LocalEmbeddingMatcher(threshold=threshold)
        self._app: Any = None

    def _ensure_model(self) -> Any:
        if self._app is not None:
            return self._app
        try:
            import insightface  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "InsightFace n'est pas installé. Installez-le avec : "
                "pip install insightface onnxruntime opencv-python-headless"
            ) from exc
        app = insightface.app.FaceAnalysis(
            name=self.model_name,
            providers=["CPUExecutionProvider"],
        )
        app.prepare(ctx_id=-1, det_size=(640, 640))
        self._app = app
        return app

    @staticmethod
    def _decode_image(image_bytes: bytes) -> Any:
        try:
            import cv2  # type: ignore[import-not-found]
            import numpy as np  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "OpenCV/NumPy requis : pip install opencv-python-headless numpy"
            ) from exc
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Impossible de décoder l'image JPEG.")
        return img

    def build_index(self) -> dict[str, int]:
        """Scan `faces/<person_name>/*.jpg|png` and save local embeddings."""
        app = self._ensure_model()
        self.matcher.known_embeddings.clear()
        counts: dict[str, int] = {}
        if not self.faces_dir.exists():
            self.faces_dir.mkdir(parents=True, exist_ok=True)
            return counts

        for person_dir in sorted(self.faces_dir.iterdir()):
            if not person_dir.is_dir():
                continue
            name = person_dir.name
            added = 0
            for img_path in sorted(person_dir.iterdir()):
                if img_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                    continue
                img = self._decode_image(img_path.read_bytes())
                faces = app.get(img)
                if not faces:
                    continue
                # Take the largest face in reference photo
                best_face = max(
                    faces,
                    key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]),
                )
                self.matcher.add_embedding(name, best_face.normed_embedding.tolist())
                added += 1
            if added:
                counts[name] = added

        self.matcher.save_index(self.index_file)
        return counts

    def load_or_build_index(self) -> None:
        if self.index_file.exists():
            self.matcher.load_index(self.index_file)
        else:
            self.build_index()

    def recognize_bytes(self, image_bytes: bytes) -> list[FaceMatch]:
        """Detect and identify all faces in a JPEG snapshot."""
        if not self.matcher.known_embeddings and self.index_file.exists():
            self.matcher.load_index(self.index_file)
        app = self._ensure_model()
        img = self._decode_image(image_bytes)
        faces = app.get(img)
        results: list[FaceMatch] = []
        for face in faces:
            bbox = [round(float(x), 1) for x in face.bbox.tolist()]
            match = self.matcher.match(face.normed_embedding.tolist(), bbox=bbox)
            results.append(match)
        return results


class CompreFaceClient:
    """Client for a self-hosted local CompreFace Docker container (recommended for HA)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        threshold: float = 0.75,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.threshold = threshold
        self.timeout = timeout

    def recognize_bytes(self, image_bytes: bytes) -> list[FaceMatch]:
        url = f"{self.base_url}/api/v1/recognition/recognize"
        resp = httpx.post(
            url,
            headers={"x-api-key": self.api_key},
            files={"file": ("snapshot.jpg", image_bytes, "image/jpeg")},
            timeout=self.timeout,
        )
        if resp.status_code == 400:
            # CompreFace returns 400 when no face is found in the image
            return []
        resp.raise_for_status()
        return self._parse_response(resp.json())

    async def async_recognize_bytes(
        self,
        image_bytes: bytes,
        client: httpx.AsyncClient,
    ) -> list[FaceMatch]:
        url = f"{self.base_url}/api/v1/recognition/recognize"
        resp = await client.post(
            url,
            headers={"x-api-key": self.api_key},
            files={"file": ("snapshot.jpg", image_bytes, "image/jpeg")},
            timeout=self.timeout,
        )
        if resp.status_code == 400:
            return []
        resp.raise_for_status()
        return self._parse_response(resp.json())

    def _parse_response(self, data: dict[str, Any]) -> list[FaceMatch]:
        matches: list[FaceMatch] = []
        for item in data.get("result") or []:
            box = item.get("box") or {}
            bbox = [
                float(box.get("x_min", 0)),
                float(box.get("y_min", 0)),
                float(box.get("x_max", 0)),
                float(box.get("y_max", 0)),
            ]
            subjects = item.get("subjects") or []
            if subjects and float(subjects[0].get("similarity", 0.0)) >= self.threshold:
                matches.append(
                    FaceMatch(
                        name=str(subjects[0]["subject"]),
                        confidence=round(float(subjects[0]["similarity"]), 4),
                        bbox=bbox,
                        is_known=True,
                    )
                )
            else:
                score = float(subjects[0].get("similarity", 0.0)) if subjects else 0.0
                matches.append(
                    FaceMatch(
                        name="Inconnu",
                        confidence=round(score, 4),
                        bbox=bbox,
                        is_known=False,
                    )
                )
        return matches
