"""
brain/fusion — Stage K: Cross-Modal Fusion.

Публичный API:
  SharedSpaceProjector          — проекция перцептов в общее 512d пространство
  EntityLinker / CrossModalLink / EntityCluster — связывание сущностей между модальностями
  ConfidenceCalibrator          — калибровка итогового confidence слияния
  CrossModalContradictionDetector / CrossModalContradiction — детекция противоречий
"""

from brain.fusion.shared_space_projector import SharedSpaceProjector
from brain.fusion.entity_linker import (
    CrossModalLink,
    EntityCluster,
    EntityLinker,
)
from brain.fusion.confidence_calibrator import ConfidenceCalibrator
from brain.fusion.cross_modal_contradiction_detector import (
    CrossModalContradiction,
    CrossModalContradictionDetector,
)

__all__ = [
    "SharedSpaceProjector",
    "CrossModalLink",
    "EntityCluster",
    "EntityLinker",
    "ConfidenceCalibrator",
    "CrossModalContradiction",
    "CrossModalContradictionDetector",
]
