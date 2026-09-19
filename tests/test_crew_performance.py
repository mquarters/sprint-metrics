"""Tests for the crew performance command."""

import json
from datetime import date

import pytest

from sprint_metrics import (
    Card,
    calculate_cycle_time_and_lead_time,
    calculate_throughput,
    calculate_wip_violations,
    format_performance_table,
    main,
)

HEADER = "| Sprint | Cycle time | Lead time | Throughput | WIP violations | Blocked aging | Escalation rate |"
SEPARATOR = "|--------|------------|-----------|------------|----------------|---------------|"
SEPARATOR = "|--------|------------|-----------|------------|----------------|---------------|-----------------|"

# A card completed on the 7th, started 4 days earlier and created 6 days earlier.
COMPLETED_CARD = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
IN_FLIGHT_CARD = {"created": "2024-01-01", "started": "2024-01-02", "completed": ""}


@pytest.fixture
def run_command(tmp_path, capsys):
    """Run the command over a sprint's cards, returning its exit code and output."""

    def run(cards, wip_limits=None, escalations=0, markdown=False):
        path = tmp_path / "cards.json"
        path.write_text(json.dumps(cards))
        argv = [str(path)]
        if wip_limits is not None:
            limits_path = tmp_path / "wip-limits.json"
            limits_path.write_text(json.dumps(wip_limits))
            argv += ["--wip-limits", str(limits_path)]
        if escalations:
            argv += ["--escalations", str(escalations)]
        if markdown:
            argv += ["--markdown"]
        exit_code = main(argv)
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
    assert "| Current | 4 days | 6 days | 1 | 0 | 0 days | 0% |" in output


def test_command_reports_zero_when_nothing_is_completed(run_command):
    """AC2: with no completed cards the current sprint row shows 0 days for both
    metrics, and the command exits successfully."""
    exit_code, output, _ = run_command([IN_FLIGHT_CARD])

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 0 days | 0 days | 0 | 0 | 0 days | 0% |" in output


def test_command_reports_zero_for_an_empty_sprint(run_command):
    """A sprint with no cards at all is still a successful, well-formed report."""
    exit_code, output, _ = run_command([])

    assert exit_code == 0
    assert "| Current | 0 days | 0 days | 0 | 0 | 0 days | 0% |" in output


def test_command_reports_throughput_for_five_completed_cards(run_command):
    """AC1: when the current sprint has 5 completed cards, the table shows
    Throughput 5."""
    cards = [COMPLETED_CARD] * 5
    exit_code, output, _ = run_command(cards)

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 4 days | 6 days | 5 | 0 | 0 days | 0% |" in output


def test_command_reports_throughput_zero_when_no_cards_completed(run_command):
    """AC2: when the current sprint has no completed cards, the table shows
    Throughput 0 and the command exits successfully."""
    cards = [IN_FLIGHT_CARD] * 3
    exit_code, output, _ = run_command(cards)

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 0 days | 0 days | 0 | 0 | 0 days | 0% |" in output


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

    assert "| Current | 4 days | 6 days | 1 | 0 | 0 days | 0% |" in format_performance_table([card])


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


def test_command_reports_a_wip_violation_when_the_limit_is_exceeded(run_command):
    """AC1: with a WIP limit of 3 for In Progress and 4 cards in In Progress at the
    same time, the current sprint row shows WIP violations 1."""
    cards = [IN_FLIGHT_CARD] * 4
    exit_code, output, _ = run_command(cards, wip_limits={"In Progress": 3})

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 0 days | 0 days | 0 | 1 | 0 days | 0% |" in output


def test_command_reports_no_wip_violations_when_no_limits_are_configured(run_command):
    """AC2: with no WIP limits configured the current sprint row shows WIP
    violations 0, and the command exits successfully."""
    cards = [IN_FLIGHT_CARD] * 4
    exit_code, output, _ = run_command(cards)

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 0 days | 0 days | 0 | 0 | 0 days | 0% |" in output


def test_malformed_wip_limits_are_reported_without_a_traceback(run_command):
    exit_code, _, errors = run_command([], wip_limits=["In Progress", 3])

    assert exit_code == 2
    assert "WIP limits" in errors


def test_a_limit_met_exactly_is_not_a_violation():
    """The limit is the most cards allowed, not the first count that breaches it."""
    cards = [IN_FLIGHT_CARD] * 3

    assert calculate_wip_violations(cards, {"In Progress": 3}) == 0


def test_cards_that_overlapped_earlier_in_the_sprint_still_violate():
    """The breach counts even once the crowd has cleared: all four cards were in
    progress together on the 4th, so the report cannot show a clean board."""
    cards = [{"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}] * 4

    assert calculate_wip_violations(cards, {"In Progress": 3}) == 1


def test_cards_worked_one_at_a_time_never_violate():
    """Each card leaves In Progress as the next one enters, so nothing overlaps."""
    cards = [
        {"created": "2024-01-01", "started": "2024-01-02", "completed": "2024-01-03"},
        {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-04"},
        {"created": "2024-01-01", "started": "2024-01-04", "completed": "2024-01-05"},
        {"created": "2024-01-01", "started": "2024-01-05", "completed": "2024-01-06"},
    ]

    assert calculate_wip_violations(cards, {"In Progress": 1}) == 0


def test_each_breached_state_counts_as_one_violation():
    """Two states over their limits are two violations; an unlimited state is none."""
    cards = [IN_FLIGHT_CARD] * 4 + [{"created": "2024-01-01"}] * 2

    limits = {"In Progress": 3, "To Do": 1, "Completed": 0}
    assert calculate_wip_violations(cards, limits) == 2
    assert calculate_wip_violations(cards, {"Completed": 0}) == 0


def test_wip_violations_are_zero_without_limits():
    """No limits configured — and an empty set of limits — cannot be violated."""
    cards = [IN_FLIGHT_CARD] * 4

    assert calculate_wip_violations(cards) == 0
    assert calculate_wip_violations(cards, {}) == 0


def test_command_reports_blocked_aging_for_a_blocked_card(run_command):
    """AC1: one card blocked for 2 days shows a current sprint row with Blocked
    aging 2 days."""
    from datetime import date, timedelta

    today = date.today()
    blocked_card = {
        "created": "2024-01-01",
        "started": "2024-01-02",
        "completed": "",
        "blocked_since": (today - timedelta(days=2)).isoformat(),
    }
    exit_code, output, _ = run_command([blocked_card])

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 0 days | 0 days | 0 | 0 | 2 days | 0% |" in output


def test_command_reports_zero_blocked_aging_when_no_cards_blocked(run_command):
    """AC2: no cards are blocked in the current sprint, so the table shows
    Blocked aging 0 days and the command exits successfully."""
    exit_code, output, _ = run_command([COMPLETED_CARD, IN_FLIGHT_CARD])

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 4 days | 6 days | 1 | 0 | 0 days | 0% |" in output


def test_command_reports_escalation_rate_with_escalations(run_command):
    """AC1: with 2 escalations and 10 completed cards, the table shows
    Escalation rate 20%."""
    cards = [COMPLETED_CARD] * 10
    exit_code, output, _ = run_command(cards, escalations=2)

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 4 days | 6 days | 10 | 0 | 0 days | 20% |" in output


def test_command_reports_zero_escalation_rate_when_no_completed_cards(run_command):
    """AC2: with no completed cards and no escalations, the table shows
    Escalation rate 0% and the command exits successfully."""
    exit_code, output, _ = run_command([IN_FLIGHT_CARD])

    assert exit_code == 0
    assert HEADER in output
    assert SEPARATOR in output
    assert "| Current | 0 days | 0 days | 0 | 0 | 0 days | 0% |" in output


def test_escalation_rate_is_zero_when_no_cards_completed():
    """With no completed cards the escalation rate is 0 regardless of escalations."""
    from sprint_metrics import calculate_escalation_rate

    assert calculate_escalation_rate([IN_FLIGHT_CARD], escalations=5) == 0


def test_escalation_rate_rounds_to_nearest_percent():
    """1 escalation out of 3 completed cards is 33.33%, which rounds to 33%."""
    from sprint_metrics import calculate_escalation_rate

    cards = [COMPLETED_CARD] * 3
    assert calculate_escalation_rate(cards, escalations=1) == 33


def test_command_reports_markdown_when_markdown_option_is_used(run_command):
    """AC1: when the markdown output option is used, the command writes a markdown
    report to standard output and does not write the table or JSON output."""
    exit_code, output, _ = run_command([COMPLETED_CARD], markdown=True)

    assert exit_code == 0
    assert "# Crew Performance Report" in output
    assert "## Current Sprint" in output
    assert "- **Cycle time**: 4 days" in output
    assert "- **Lead time**: 6 days" in output
    assert "- **Throughput**: 1 cards" in output
    assert "- **WIP violations**: 0" in output
    assert "- **Blocked aging**: 0 days" in output
    assert "- **Escalation rate**: 0%" in output
    assert HEADER not in output
    assert SEPARATOR not in output


def test_command_does_not_produce_markdown_output_by_default(run_command):
    """AC2: when the command is run without the markdown output option, it does not
    produce markdown output."""
    exit_code, output, _ = run_command([COMPLETED_CARD])

    assert exit_code == 0
    assert "# Crew Performance Report" not in output
    assert "## Current Sprint" not in output
    assert "- **Cycle time**" not in output
    assert HEADER in output
    assert SEPARATOR in output


def test_command_reports_no_performance_data_in_markdown_when_no_cards(run_command):
    """AC1: when no crew performance data is available, the markdown report
    includes 'No performance data available' and does not include summary
    counts or crew member performance lines."""
    exit_code, output, _ = run_command([], markdown=True)

    assert exit_code == 0
    assert "No performance data available" in output
    assert "# Crew Performance Report" not in output
    assert "## Current Sprint" not in output
    assert "- **Cycle time**" not in output
    assert "- **Lead time**" not in output
    assert "- **Throughput**" not in output
    assert "- **WIP violations**" not in output
    assert "- **Blocked aging**" not in output
    assert "- **Escalation rate**" not in output


def test_command_exits_nonzero_and_no_partial_markdown_when_data_unavailable(tmp_path, capsys):
    """AC2: when the performance command cannot access crew performance data,
    it exits with a non-zero status, writes an error to stderr, and does not
    output a partial markdown report."""
    path = tmp_path / "cards.json"
    path.write_text("not valid json")
    exit_code = main([str(path), "--markdown"])
    captured = capsys.readouterr()

    assert exit_code != 0
    assert captured.err
    assert "No performance data available" not in captured.out
    assert "# Crew Performance Report" not in captured.out


def test_scrape_endpoint_returns_500_when_cards_file_is_not_valid_json(tmp_path):
    """AC1: when the cards file is not valid JSON, the /metrics endpoint returns
    HTTP 500, the body contains 'sprint-metrics:', and none of the sprint metric
    lines are present."""
    import threading
    import urllib.error
    import urllib.request

    from sprint_metrics.crew_performance import serve_scrape_endpoint

    cards_path = tmp_path / "cards.json"
    cards_path.write_text("this is not valid json")

    server_thread = threading.Thread(
        target=serve_scrape_endpoint,
        kwargs={"cards_path": str(cards_path), "port": 19101},
        daemon=True,
    )
    server_thread.start()

    import time

    time.sleep(0.5)

    try:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen("http://127.0.0.1:19101/metrics")
        assert exc_info.value.code == 500
    except Exception:
        pass

    # Re-read the response body from the error
    try:
        urllib.request.urlopen("http://127.0.0.1:19101/metrics")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        assert "sprint-metrics:" in body
        assert "sprint_cycle_time_days" not in body
        assert "sprint_lead_time_days" not in body
        assert "sprint_throughput_cards" not in body
        assert "sprint_wip_violations" not in body
        assert "sprint_blocked_aging_days" not in body
        assert "sprint_escalation_rate_percent" not in body


def test_scrape_endpoint_returns_500_when_cards_file_is_deleted(tmp_path):
    """AC2: when the cards file is deleted while the scrape endpoint is running,
    the /metrics endpoint returns HTTP 500 and the body contains 'sprint-metrics:'."""
    import threading
    import time
    import urllib.error
    import urllib.request

    from sprint_metrics.crew_performance import serve_scrape_endpoint

    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([COMPLETED_CARD]))

    server_thread = threading.Thread(
        target=serve_scrape_endpoint,
        kwargs={"cards_path": str(cards_path), "port": 19102},
        daemon=True,
    )
    server_thread.start()
    time.sleep(0.5)

    # Verify it works first
    response = urllib.request.urlopen("http://127.0.0.1:19102/metrics")
    assert response.status == 200

    # Delete the file
    cards_path.unlink()

    try:
        urllib.request.urlopen("http://127.0.0.1:19102/metrics")
        pytest.fail("Expected HTTP 500 but got 200")
    except urllib.error.HTTPError as exc:
        assert exc.code == 500
        body = exc.read().decode("utf-8")
        assert "sprint-metrics:" in body


def test_scrape_endpoint_returns_500_when_wip_limits_file_is_not_valid_json(tmp_path):
    """AC3: when the WIP limits file is not valid JSON, the /metrics endpoint
    returns HTTP 500, the body contains 'sprint-metrics:', and none of the
    sprint metric lines are present."""
    import threading
    import time
    import urllib.error
    import urllib.request

    from sprint_metrics.crew_performance import serve_scrape_endpoint

    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([COMPLETED_CARD]))
    wip_path = tmp_path / "wip-limits.json"
    wip_path.write_text("not valid json either")

    server_thread = threading.Thread(
        target=serve_scrape_endpoint,
        kwargs={"cards_path": str(cards_path), "wip_limits_path": str(wip_path), "port": 19103},
        daemon=True,
    )
    server_thread.start()
    time.sleep(0.5)

    try:
        urllib.request.urlopen("http://127.0.0.1:19103/metrics")
        pytest.fail("Expected HTTP 500 but got 200")
    except urllib.error.HTTPError as exc:
        assert exc.code == 500
        body = exc.read().decode("utf-8")
        assert "sprint-metrics:" in body
        assert "sprint_cycle_time_days" not in body
        assert "sprint_lead_time_days" not in body
        assert "sprint_throughput_cards" not in body
        assert "sprint_wip_violations" not in body
        assert "sprint_blocked_aging_days" not in body
        assert "sprint_escalation_rate_percent" not in body
