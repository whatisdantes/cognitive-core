"""
brain/fusion/shared_space_projector.py — Проекция векторов в единое пространство.

Выравнивает embeddings разных модальностей в shared latent space 512d:
  text(768d)  → W_text(768×512)  → 512d (L2-norm)
  audio(768d) → W_audio(768×512) → 512d (L2-norm)
  image(512d) → identity         → 512d (L2-norm)

Матрицы инициализируются Xavier uniform и могут быть сохранены/загружены (JSON).
Нет новых pip-зависимостей — только numpy.
"""
from __future__ import annotations

import json
import logging
import math
import os
from typing import Any, Dict, List, Optional

try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    _NUMPY_AVAILABLE = False

from brain.core.contracts import EncodedPercept, Modality

logger = logging.getLogger(__name__)


def _xavier_uniform(fan_in: int, fan_out: int, rng: Any) -> Any:
    """Xavier uniform инициализация матрицы (fan_in × fan_out)."""
    limit = math.sqrt(6.0 / (fan_in + fan_out))
    return rng.uniform(-limit, limit, (fan_in, fan_out)).astype(np.float32)


def _l2_normalize(vec: Any) -> Any:
    """L2-нормализация numpy вектора. Возвращает нулевой вектор если норма=0."""
    norm = float(np.linalg.norm(vec))
    if norm < 1e-10:
        return np.zeros_like(vec)
    return vec / norm


def _pad_or_truncate(vec: Any, target_dim: int) -> Any:
    """Привести вектор к target_dim через padding нулями или truncation."""
    current = len(vec)
    if current == target_dim:
        return vec
    if current > target_dim:
        return vec[:target_dim]
    padded = np.zeros(target_dim, dtype=np.float32)
    padded[:current] = vec
    return padded


class SharedSpaceProjector:
    """
    Проецирует векторы разных модальностей в shared latent space TARGET_DIM.

    Использование:
        ssp = SharedSpaceProjector(seed=42)
        proj = ssp.project(text_vector_768d, Modality.TEXT)   # → List[float] 512d
        proj = ssp.project(image_vector_512d, Modality.IMAGE) # → List[float] 512d
        ssp.save("matrices.json")
        ssp.load("matrices.json")
    """

    TARGET_DIM: int = 512

    def __init__(
        self,
        text_input_dim: int = 768,
        audio_input_dim: int = 768,
        target_dim: int = 512,
        seed: Optional[int] = None,
    ) -> None:
        if not _NUMPY_AVAILABLE:
            raise ImportError("numpy is required for SharedSpaceProjector")

        self._text_input_dim = text_input_dim
        self._audio_input_dim = audio_input_dim
        self.TARGET_DIM = target_dim

        rng = np.random.RandomState(seed)
        self._W_text: Any = _xavier_uniform(text_input_dim, target_dim, rng)
        self._W_audio: Any = _xavier_uniform(audio_input_dim, target_dim, rng)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def project(self, vector: List[float], modality: Modality) -> List[float]:
        """
        Проецировать вектор в shared space TARGET_DIM.

        Возвращает L2-нормализованный вектор длиной TARGET_DIM.
        Если вектор пуст или нулевой — возвращает [0.0] * TARGET_DIM.
        """
        if not vector or all(v == 0.0 for v in vector):
            return [0.0] * self.TARGET_DIM

        vec = np.array(vector, dtype=np.float32)

        if modality == Modality.TEXT:
            vec = _pad_or_truncate(vec, self._text_input_dim)
            projected = vec @ self._W_text
        elif modality == Modality.AUDIO:
            vec = _pad_or_truncate(vec, self._audio_input_dim)
            projected = vec @ self._W_audio
        else:
            # IMAGE, VIDEO, FUSED — identity (pad/truncate to TARGET_DIM)
            projected = _pad_or_truncate(vec, self.TARGET_DIM)

        return list(_l2_normalize(projected).tolist())

    def project_percept(self, percept: EncodedPercept) -> List[float]:
        """Удобный метод: project(percept.vector, percept.modality)."""
        return self.project(percept.vector, percept.modality)

    def project_all(self, percepts: List[EncodedPercept]) -> List[List[float]]:
        """Проецировать список перцептов. Возвращает список TARGET_DIM векторов."""
        return [self.project_percept(p) for p in percepts]

    def save(self, path: str) -> None:
        """Сохранить матрицы проекции в JSON (numpy tolist)."""
        dirpath = os.path.dirname(path)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)
        data = {
            "text_input_dim": self._text_input_dim,
            "audio_input_dim": self._audio_input_dim,
            "target_dim": self.TARGET_DIM,
            "W_text": self._W_text.tolist(),
            "W_audio": self._W_audio.tolist(),
        }
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, path)
        logger.info("[SharedSpaceProjector] saved to %s", path)

    def load(self, path: str) -> None:
        """Загрузить матрицы проекции из JSON."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._text_input_dim = data["text_input_dim"]
        self._audio_input_dim = data["audio_input_dim"]
        self.TARGET_DIM = data["target_dim"]
        self._W_text = np.array(data["W_text"], dtype=np.float32)
        self._W_audio = np.array(data["W_audio"], dtype=np.float32)
        logger.info("[SharedSpaceProjector] loaded from %s", path)

    def status(self) -> Dict[str, Any]:
        """Статус проектора."""
        return {
            "target_dim": self.TARGET_DIM,
            "text_input_dim": self._text_input_dim,
            "audio_input_dim": self._audio_input_dim,
            "W_text_shape": list(self._W_text.shape),
            "W_audio_shape": list(self._W_audio.shape),
        }
