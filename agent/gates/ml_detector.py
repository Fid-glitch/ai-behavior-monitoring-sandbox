# agent/gates/ml_detector.py
import warnings
from pathlib import Path
import joblib


class MLDetector:
    """Wrapper to load and run Member 2's TF-IDF + LogisticRegression model."""

    _instance = None

    def __init__(self):
        self.vectorizer = None
        self.classifier = None
        self.is_loaded = False
        self._load_models()

    def _load_models(self):
        # Locate Member 2's models in detection/models/
        model_dir = Path(__file__).parent.parent.parent / "detection" / "models"
        vec_path = model_dir / "tfidf_vectorizer.joblib"
        clf_path = model_dir / "injection_classifier.joblib"

        if vec_path.exists() and clf_path.exists():
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    self.vectorizer = joblib.load(vec_path)
                    self.classifier = joblib.load(clf_path)
                self.is_loaded = True
            except Exception as e:
                print(f"[MLDetector] Warning: Failed to load detection model: {e}")

    def predict_risk(self, text: str) -> float:
        """Returns prompt injection probability between 0.0 and 1.0."""
        if not self.is_loaded or not text or not text.strip():
            return 0.0
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                X = self.vectorizer.transform([text])
                probs = self.classifier.predict_proba(X)
                return float(probs[0][1])
        except Exception:
            return 0.0