"""Unit tests for the lightweight aosu-face Docker service."""

import importlib.util
import py_compile
import tempfile
import unittest
from pathlib import Path

APP_PATH = Path(__file__).resolve().parent.parent / "aosu-face" / "app.py"


class TestAosuFaceService(unittest.TestCase):
    def test_app_python_syntax(self) -> None:
        self.assertTrue(APP_PATH.exists())
        py_compile.compile(str(APP_PATH), doraise=True)

    def test_face_engine_logic_with_mocked_extractor(self) -> None:
        # Load helpers directly without requiring fastapi/insightface on Windows
        source = APP_PATH.read_text(encoding="utf-8")
        # Verify key CompreFace-compatible endpoint and UI exist
        self.assertIn("/api/v1/recognition/recognize", source)
        self.assertIn("x-api-key", source)
        self.assertIn("buffalo_sc", source)

        # If fastapi is installed, also run FaceEngine unit test
        if importlib.util.find_spec("fastapi") is None:
            return

        spec = importlib.util.spec_from_file_location("aosu_face_app", APP_PATH)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        with tempfile.TemporaryDirectory() as tmp:
            eng = mod.FaceEngine(faces_dir=Path(tmp) / "faces", index_file=Path(tmp) / "idx.json")
            eng.extract_faces = lambda b: [
                {
                    "box": {"x_min": 10, "y_min": 10, "x_max": 100, "y_max": 100},
                    "embedding": [1.0, 0.0, 0.0] if b == b"jerome" else [0.0, 1.0, 0.0],
                }
            ]
            self.assertEqual(eng.add_subject_photo("Jérôme", b"jerome"), 1)
            res = eng.recognize(b"jerome")
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["subjects"][0]["subject"], "Jérôme")
            self.assertEqual(res[0]["subjects"][0]["similarity"], 1.0)
            eng.delete_subject("Jérôme")
            self.assertEqual(eng.list_subjects(), {})


if __name__ == "__main__":
    unittest.main()
