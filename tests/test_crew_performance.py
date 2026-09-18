"""Tests for the crew performance command."""

import json
from datetime import date

import pytest

from sprint_metrics import (
    Card,
    calculate_cycle_time_and_lead_time,
    calculate_throughput,
    format_performance_table,
    main,
)

HEADER = "| Sprint | Cycle time | Lead time | Throughput |"
SEPARATOR = "|--------|------------|-----------|------------|"

# A card completed on the 7th, started 4 days earlier and created 6 days earlier.
COMPLETED_CARD = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
IN_FLIGHT_CARD = {"created": "2024-01-01", "started": "2024-01-02", "completed": ""}


@pytest.fixture
def run_command(tmp_path, capsys):
    """Run the command over a sprint's cards, returning its exit code and output."""

    def run(cards):
        path = tmp_path / "cards.json"
        path.write_text(json.dumps(cards))
        exit_code = main([str(path)])
        captured = capsys.readouterr()
        return exit_code, captured.out, captured.err

    return run


def test_command_reports_cycle_and_lead_time_for_a_completed_card(run_command):
    """AC1: one card started 4 days and created 6 days before it completed shows
    a current sprint row with Cycle time 4 days and Lead time 6 days."""
    exit_code, output, _ = run_command([COMPLETED_CARD])

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 4 days | 6 days | 1 |" in output


def test_command_reports_zero_when_nothing_is_completed(run_command):
    """AC2: with no completed cards the current sprint row shows 0 days for both
    metrics, and the command exits successfully."""
    exit_code, output, _ = run_command([IN_FLIGHT_CARD])

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 0 days | 0 days | 0 |" in output


def test_command_reports_zero_for_an_empty_sprint(run_command):
    """A sprint with no cards at all is still a successful, well-formed report."""
    exit_code, output, _ = run_command([])

    assert exit_code == 0
    assert "| Current | 0 days | 0 days | 0 |" in output


def test_command_reports_throughput_for_five_completed_cards(run_command):
    """AC1: when the current sprint has 5 completed cards, the table shows
    Throughput 5."""
    cards = [COMPLETED_CARD] * 5
    exit_code, output, _ = run_command(cards)

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 4 days | 6 days | 5 |" in output


def test_command_reports_throughput_zero_when_no_cards_completed(run_command):
    """AC2: when the current sprint has no completed cards, the table shows
    Throughput 0 and the command exits successfully."""
    cards = [IN_FLIGHT_CARD] * 3
    exit_code, output, _ = run_command(cards)

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 0 days | 0 days | 0 |" in output


def test_malformed_dates_are_reported_without_a_traceback(run_command):
    exit_code, _, errors = run_command([{"created": "not-a-date"}])

    assert exit_code == 2
    assert "not-a-date" in errors


def test_cycle_and_lead_time_of_a_completed_card():
    assert calculate_cycle_time_and_lead_time([COMPLETED_CARD]) == (4, 6)


def test_in_flight_cards_do_not_count_towards_the_metrics():
    assert calculate_cycle_time_and_lead_time([IN_FLIGHT_CARD]) == (0, 0)


def test_metrics_average_across_completed_cards():
    """Two completed cards report the mean, not the total."""
    slower_card = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-09"}

    assert calculate_cycle_time_and_lead_time([COMPLETED_CARD, slower_card]) == (5, 7)


def test_completed_card_that_was_never_started_has_no_cycle_time():
    """Lead time is still measurable without a start date; cycle time is not."""
    card = Card(created=date(2024, 1, 1), completed=date(2024, 1, 7))

    assert calculate_cycle_time_and_lead_time([card]) == (0, 6)


def test_cards_may_be_passed_as_dataclasses():
    card = Card(created=date(2024, 1, 1), started=date(2024, 1, 3), completed=date(2024, 1, 7))

    assert "| Current | 4 days | 6 days | 1 |" in format_performance_table([card])


def test_throughput_counts_completed_cards():
    """Throughput is the count of completed cards."""
    cards = [COMPLETED_CARD, IN_FLIGHT_CARD, COMPLETED_CARD]
    assert calculate_throughput(cards) == 2


def test_throughput_is_zero_when_nothing_is_completed():
    """A sprint with only in-flight cards has zero throughput."""
    cards = [IN_FLIGHT_CARD, IN_FLIGHT_CARD]
    assert calculate_throughput(cards) == 0


def test_throughput_is_zero_for_an_empty_sprint():
    """An empty sprint has zero throughput."""
    assert calculate_throughput([]) == 0
