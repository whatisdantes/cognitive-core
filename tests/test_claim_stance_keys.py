from brain.core.text_utils import build_claim_grouping_keys, normalize_concept


def test_numeric_claims_share_family_but_keep_stance():
    concept = normalize_concept("Рабочая память")

    family_a, stance_a = build_claim_grouping_keys(
        concept,
        "Рабочая память содержит 7 элементов",
    )
    family_a2, stance_a2 = build_claim_grouping_keys(
        concept,
        "Рабочая память оперирует 7 элементами",
    )
    family_b, stance_b = build_claim_grouping_keys(
        concept,
        "Рабочая память содержит 4 элемента",
    )

    assert family_a == family_a2 == family_b
    assert stance_a == stance_a2
    assert stance_b != stance_a


def test_numeric_range_and_center_share_stance():
    concept = normalize_concept("Рабочая память")

    family_range, stance_range = build_claim_grouping_keys(
        concept,
        "рабочая память содержит 7±2 элементов",
    )
    family_center, stance_center = build_claim_grouping_keys(
        concept,
        "рабочая память оперирует 7 элементами",
    )
    family_other, stance_other = build_claim_grouping_keys(
        concept,
        "рабочая память содержит 4±1 элемента",
    )

    assert family_range == family_center == family_other
    assert stance_range == stance_center
    assert stance_other != stance_range


def test_text_claims_get_stable_keys():
    first = build_claim_grouping_keys("python", "Python это язык программирования")
    second = build_claim_grouping_keys(" Python ", "python это язык программирования!")

    assert first == second
