"""Unit tests for local facial recognition and Home Assistant component integrity."""

import json
import py_compile
import tempfile
import unittest
from pathlib import Path

from aosu.face_recognition import (
    CompreFaceClient,
    LocalEmbeddingMatcher,
    cosine_similarity,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
HA_DIR = REPO_ROOT / "custom_components" / "aosu"


class TestFaceRecognitionAndHAComponent(unittest.TestCase):
    def test_cosine_similarity_and_matcher(self) -> None:
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [1.0, 0.0]), 1.0)
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)

        matcher = LocalEmbeddingMatcher(threshold=0.8)
        matcher.add_embedding("Jerome", [0.9, 0.1, 0.0])
        matcher.add_embedding("Jules", [0.0, 0.9, 0.1])

        m1 = matcher.match([0.92, 0.08, 0.0])
        self.assertTrue(m1.is_known)
        self.assertEqual(m1.name, "Jerome")

        m2 = matcher.match([0.0, 0.0, 1.0])
        self.assertFalse(m2.is_known)
        self.assertEqual(m2.name, "Inconnu")

        with tempfile.TemporaryDirectory() as tmp:
            idx = Path(tmp) / "faces_index.json"
            matcher.save_index(idx)
            matcher2 = LocalEmbeddingMatcher(threshold=0.8)
            matcher2.load_index(idx)
            self.assertEqual(matcher2.match([0.0, 0.95, 0.05]).name, "Jules")

    def test_compreface_response_parsing(self) -> None:
        client = CompreFaceClient("http://localhost:8000", "test-key", threshold=0.75)
        parsed = client._parse_response(
            {
                "result": [
                    {
                        "box": {"x_min": 10, "y_min": 20, "x_max": 110, "y_max": 120},
                        "subjects": [{"subject": "Jerome", "similarity": 0.91}],
                    },
                    {
                        "box": {"x_min": 200, "y_min": 30, "x_max": 280, "y_max": 110},
                        "subjects": [{"subject": "Eliott", "similarity": 0.42}],
                    },
                ]
            }
        )
        self.assertEqual(len(parsed), 2)
        self.assertTrue(parsed[0].is_known)
        self.assertEqual(parsed[0].name, "Jerome")
        self.assertFalse(parsed[1].is_known)
        self.assertEqual(parsed[1].name, "Inconnu")

    def test_ha_component_json_and_python_syntax(self) -> None:
        for json_file in [
            HA_DIR / "manifest.json",
            HA_DIR / "strings.json",
            HA_DIR / "translations" / "fr.json",
            HA_DIR / "translations" / "en.json",
        ]:
            self.assertTrue(json_file.exists(), f"Missing {json_file}")
            parsed = json.loads(json_file.read_text(encoding="utf-8"))
            self.assertIsInstance(parsed, dict)

        manifest = json.loads((HA_DIR / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["domain"], "aosu")
        self.assertTrue(manifest["config_flow"])

        py_files = list(HA_DIR.glob("*.py"))
        self.assertGreaterEqual(len(py_files), 7)
        for py_file in py_files:
            py_compile.compile(str(py_file), doraise=True)


if __name__ == "__main__":
    unittest.main()
