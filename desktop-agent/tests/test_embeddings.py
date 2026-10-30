from __future__ import annotations

import math

import pytest

from omniagent_pc.embeddings import DIM, VERIFY_THRESHOLD, cosine, embed, normalize, similarity


def test_embedding_has_64_dimensions_and_unit_length() -> None:
    vector = embed("Hello from OmniAgent")
    assert len(vector) == DIM == 64
    assert math.isclose(sum(v * v for v in vector), 1.0, rel_tol=1e-9)


def test_embedding_is_deterministic_across_calls() -> None:
    assert embed("save the file") == embed("save the file")


def test_empty_text_embeds_to_zero_and_never_matches() -> None:
    assert embed("   ") == [0.0] * DIM
    assert similarity("hello", "") == 0.0
    assert similarity("", "hello") == 0.0


def test_case_and_punctuation_do_not_matter() -> None:
    assert normalize("Hello,  WORLD!!") == "hello world"
    assert cosine(embed("Hello, World!"), embed("hello world")) == pytest.approx(1.0)


def test_verbatim_text_scores_one_even_inside_a_lot_of_other_text() -> None:
    screen = "Untitled - Notepad File Edit Format View Dear team thank you for your hard work Help"
    assert similarity("Thank you for your hard work", screen) == 1.0


def test_similar_text_clears_the_threshold() -> None:
    screen = "Untitled Notepad Thank you team for the hard work this quarter"
    assert similarity("thank you team for your hard work", screen) >= VERIFY_THRESHOLD


def test_unrelated_text_stays_below_the_threshold() -> None:
    screen = "Untitled - Notepad File Edit Format View Help quarterly budget spreadsheet totals"
    assert similarity("Dear team thank you for your hard work", screen) < VERIFY_THRESHOLD


def test_a_typo_still_matches() -> None:
    assert similarity("hello from omniagent", "hello from omniagnt") >= VERIFY_THRESHOLD


def test_the_best_window_is_used_not_the_whole_screen() -> None:
    padding = " ".join(f"filler{i}" for i in range(200))
    assert similarity("send the report today", f"{padding} send the report todays {padding}") >= VERIFY_THRESHOLD


def test_cosine_of_different_texts_is_lower_than_identical() -> None:
    assert cosine(embed("open notepad"), embed("open notepad")) > cosine(embed("open notepad"), embed("close chrome"))
