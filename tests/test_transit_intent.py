import pytest

from dn_home.intents.transit import TransitNextIntent, parse_transit_intent


@pytest.mark.parametrize(
    ("text", "destination"),
    (
        ("Qual é o próximo comboio para o trabalho?", "work"),
        ("Qual é o próximo comboio para Paris?", "paris"),
        ("Quando passa o próximo RER para Paris?", "paris"),
        ("Quando é o próximo para o trabalho?", "work"),
        ("próximo comboio para o trabalho", "work"),
        ("próximo RER para Paris", "paris"),
    ),
)
def test_parses_approved_transit_commands(text: str, destination: str) -> None:
    assert parse_transit_intent(text) == TransitNextIntent(destination)


@pytest.mark.parametrize(
    "text",
    (
        "Liga a luz do quarto",
        "Vai para Paris",
        "Qual é o próximo autocarro para Lisboa?",
        "",
    ),
)
def test_unknown_intent_does_not_invent_action(text: str) -> None:
    assert parse_transit_intent(text) is None
