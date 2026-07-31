"""Tests for m/z helpers in the results viewer."""

import pytest

from results_viewer import mass_group_key, parse_mass_value


def test_parse_mass_value():
    assert parse_mass_value("538.18168764527") == pytest.approx(538.18168764527)
    assert parse_mass_value("NA") is None
    assert parse_mass_value("") is None


def test_mass_group_key_groups_close_values():
    assert mass_group_key("538.18168764527") == mass_group_key("538.18168764528")
