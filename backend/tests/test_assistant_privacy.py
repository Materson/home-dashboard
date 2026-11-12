"""Aliases for private data sent to cloud models."""

from __future__ import annotations

from apps.assistant.privacy import Passthrough, Pseudonymizer, valid_pesel


def p():
    return Pseudonymizer(names=["Zosia", "Mateusz Kowalski", "Mama"])


def test_names_with_polish_case_endings():
    ps = p()
    out = ps.hide("Co dać Zosi na gorączkę? Zosia ma 4 lata, a Mateuszowi kupiłem lek.")
    assert "Zosi" not in out and "Mateusz" not in out
    assert out.count("[P") == 3
    zosia = ps.hide("Zosia")
    assert ps.reveal(f"{zosia} może dostać paracetamol") == "Zosia może dostać paracetamol"


def test_same_person_same_alias_and_bare_alias_revealed():
    ps = p()
    first = ps.hide("Zosia")
    assert ps.hide("dla Zosi") == f"dla {first}"
    assert ps.reveal(f"Dawka dla {first[1:-1]} to 5 ml") == "Dawka dla Zosia to 5 ml"


def test_everyday_words_are_not_names():
    assert p().hide("Czy mamy mleko?") == "Czy mamy mleko?"


def test_identifiers_and_addresses():
    ps = p()
    text = (
        "PESEL 44051401359, tel. +48 600 100 200, mail jan.kowalski@example.com, "
        "mieszkamy ul. Długa 5/3, 00-950 Warszawa, ur. 12.03.2019, "
        "konto PL61 1090 1014 0000 0712 1981 2874"
    )
    out = ps.hide(text)
    for secret in (
        "44051401359",
        "600 100 200",
        "example.com",
        "Długa",
        "00-950",
        "12.03.2019",
        "1981",
    ):
        assert secret not in out, secret
    assert ps.reveal(out) == text


def test_not_a_pesel_is_left_alone():
    assert not valid_pesel("12345678901")
    assert "12345678901" in p().hide("zamówienie 12345678901")


def test_tool_results_are_walked():
    ps = p()
    out = ps.hide_obj({"person": "Zosia", "items": [{"note": "dzwonić 600100200"}], "n": 3})
    assert out["person"].startswith("[P") and "600100200" not in str(out) and out["n"] == 3


def test_aliases_survive_between_turns():
    ps = p()
    ps.hide("Zosia i Mama")
    again = Pseudonymizer(aliases=ps.aliases, names=["Zosia", "Mama"])
    assert again.hide("Mama") == ps.hide("Mama")


def test_local_model_gets_real_text():
    assert Passthrough(names=["Zosia"]).hide("Zosia 600100200") == "Zosia 600100200"
