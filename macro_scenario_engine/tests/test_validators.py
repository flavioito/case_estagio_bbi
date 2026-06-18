from __future__ import annotations

import pytest

from app.validators import InputValidationError, OutputValidationError, validate_input_scenario, validate_known_factors


def test_empty_input_raises_error() -> None:
    with pytest.raises(InputValidationError):
        validate_input_scenario("")


def test_short_input_raises_error() -> None:
    with pytest.raises(InputValidationError):
        validate_input_scenario("Selic")


def test_personalized_recommendation_is_rejected() -> None:
    with pytest.raises(InputValidationError):
        validate_input_scenario("Qual ação devo comprar hoje para ganhar dinheiro?")


def test_unknown_factor_is_rejected() -> None:
    with pytest.raises(OutputValidationError):
        validate_known_factors(["selic_down", "invented_factor"], {"selic_down"})

