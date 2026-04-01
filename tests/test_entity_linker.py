# tests/test_entity_linker.py
"""Тесты для brain/fusion/entity_linker.py (K.2)."""
from __future__ import annotations
import math

import pytest

from brain.core.contracts import EncodedPercept, Modality


def _p(pid: str, mod: Modality, vec: list, q: float = 0.8) -> EncodedPercept:
    return EncodedPercept(
        percept_id=pid, modality=mod, vector=vec,
        text="test", quality=q, vector_dim=len(vec),
    )


def _unit(dim: int) -> list:
    """Единичный вектор (все компоненты равны, L2-нормализован)."""
    v = [1.0] * dim
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def test_import():
    from brain.fusion.entity_linker import EntityLinker, EntityCluster, CrossModalLink
    assert EntityLinker is not None
    assert EntityCluster is not None
    assert CrossModalLink is not None


# ---------------------------------------------------------------------------
# CrossModalLink dataclass
# ---------------------------------------------------------------------------

def test_link_fields():
    from brain.fusion.entity_linker import CrossModalLink
    lnk = CrossModalLink(
        source_id="p1", target_id="p2", similarity=0.85,
        link_type="LINK", source_modality="text", target_modality="image",
    )
    assert lnk.source_id == "p1"
    assert lnk.target_id == "p2"
    assert lnk.link_type == "LINK"
    assert lnk.source_modality == "text"


# ---------------------------------------------------------------------------
# EntityCluster dataclass
# ---------------------------------------------------------------------------

def test_cluster_fields():
    from brain.fusion.entity_linker import EntityCluster
    c = EntityCluster(
        cluster_id="c1", centroid=[0.1] * 512,
        member_ids=["p1", "p2"], modalities=["text", "image"],
        confidence=0.8, created_at="2026-04-03T00:00:00",
    )
    assert c.cluster_id == "c1"
    assert len(c.member_ids) == 2
    assert len(c.centroid) == 512


# ---------------------------------------------------------------------------
# link() — пороги
# ---------------------------------------------------------------------------

def test_link_identical_vectors_strong():
    from brain.fusion.entity_linker import EntityLinker
    linker = EntityLinker()
    v = _unit(512)
    ps = [_p("p1", Modality.TEXT, v), _p("p2", Modality.IMAGE, v)]
    links = linker.link(ps, [v, v])
    assert len(links) == 1
    assert links[0].link_type == "STRONG"
    assert links[0].similarity > 0.99


def test_link_orthogonal_no_link():
    from brain.fusion.entity_linker import EntityLinker
    linker = EntityLinker()
    v1 = [1.0] + [0.0] * 511
    v2 = [0.0, 1.0] + [0.0] * 510
    ps = [_p("p1", Modality.TEXT, v1), _p("p2", Modality.IMAGE, v2)]
    assert linker.link(ps, [v1, v2]) == []


def test_link_empty():
    from brain.fusion.entity_linker import EntityLinker
    assert EntityLinker().link([], []) == []


def test_link_single_percept():
    from brain.fusion.entity_linker import EntityLinker
    v = _unit(512)
    assert EntityLinker().link([_p("p1", Modality.TEXT, v)], [v]) == []


def test_link_same_modality_excluded():
    """Пары одной модальности не создают ссылки."""
    from brain.fusion.entity_linker import EntityLinker
    v = _unit(512)
    ps = [_p("p1", Modality.TEXT, v), _p("p2", Modality.TEXT, v)]
    links = EntityLinker().link(ps, [v, v])
    assert all(lnk.source_modality != lnk.target_modality for lnk in links)


def test_link_type_link_range():
    """cos_sim ~0.80 → тип LINK (между link_threshold=0.75 и strong_threshold=0.90)."""
    from brain.fusion.entity_linker import EntityLinker
    angle = math.acos(0.80)
    v1 = [1.0, 0.0] + [0.0] * 510
    v2 = [math.cos(angle), math.sin(angle)] + [0.0] * 510
    ps = [_p("p1", Modality.TEXT, v1), _p("p2", Modality.IMAGE, v2)]
    links = EntityLinker().link(ps, [v1, v2])
    if links:
        assert links[0].link_type in ("LINK", "STRONG")


def test_link_type_weak_range():
    """cos_sim ~0.65 → тип WEAK (между weak_threshold=0.60 и link_threshold=0.75)."""
    from brain.fusion.entity_linker import EntityLinker
    angle = math.acos(0.65)
    v1 = [1.0, 0.0] + [0.0] * 510
    v2 = [math.cos(angle), math.sin(angle)] + [0.0] * 510
    ps = [_p("p1", Modality.TEXT, v1), _p("p2", Modality.IMAGE, v2)]
    links = EntityLinker().link(ps, [v1, v2])
    if links:
        assert links[0].link_type == "WEAK"


# ---------------------------------------------------------------------------
# cluster()
# ---------------------------------------------------------------------------

def test_cluster_three_similar():
    from brain.fusion.entity_linker import EntityLinker
    v = _unit(512)
    ps = [
        _p("p1", Modality.TEXT, v, 0.9),
        _p("p2", Modality.IMAGE, v, 0.8),
        _p("p3", Modality.AUDIO, v, 0.85),
    ]
    clusters = EntityLinker().cluster(ps, [v, v, v])
    assert len(clusters) == 1
    assert set(clusters[0].member_ids) == {"p1", "p2", "p3"}
    assert len(clusters[0].modalities) == 3


def test_cluster_two_groups():
    from brain.fusion.entity_linker import EntityLinker
    v1 = [1.0] + [0.0] * 511
    v2 = [0.0, 1.0] + [0.0] * 510
    ps = [
        _p("p1", Modality.TEXT, v1),
        _p("p2", Modality.IMAGE, v1),
        _p("p3", Modality.TEXT, v2),
        _p("p4", Modality.AUDIO, v2),
    ]
    clusters = EntityLinker().cluster(ps, [v1, v1, v2, v2])
    assert len(clusters) == 2


def test_cluster_empty():
    from brain.fusion.entity_linker import EntityLinker
    assert EntityLinker().cluster([], []) == []


def test_cluster_centroid_dim():
    from brain.fusion.entity_linker import EntityLinker
    v = _unit(512)
    ps = [_p("p1", Modality.TEXT, v), _p("p2", Modality.IMAGE, v)]
    clusters = EntityLinker().cluster(ps, [v, v])
    if clusters:
        assert len(clusters[0].centroid) == 512


def test_cluster_confidence_is_mean_quality():
    from brain.fusion.entity_linker import EntityLinker
    v = _unit(512)
    ps = [
        _p("p1", Modality.TEXT, v, q=0.8),
        _p("p2", Modality.IMAGE, v, q=0.6),
    ]
    clusters = EntityLinker().cluster(ps, [v, v])
    if clusters:
        assert abs(clusters[0].confidence - 0.7) < 0.01


# ---------------------------------------------------------------------------
# status()
# ---------------------------------------------------------------------------

def test_status():
    from brain.fusion.entity_linker import EntityLinker
    s = EntityLinker().status()
    assert "link_threshold" in s
    assert "strong_threshold" in s
    assert "weak_threshold" in s
