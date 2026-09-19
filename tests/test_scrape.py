"""Tests for the scrape endpoint that serves sprint metrics."""

import json
import threading
import time
import urllib.request

from sprint_metrics.scrape import serve_metrics

COMPLETED_CARD = {"created": "2024-01-01", "started": "2024-01-03", "completed": "2024-01-07"}
IN_FLIGHT_CARD = {"created": "2024-01-01", "started": "2024-01-02", "completed": ""}


def _start_server(
    cards_path: str,
    port: int,
    wip_limits_path: str | None = None,
    escalations: int = 0,
) -> threading.Thread:
    """Start the metrics server in a background thread."""
    thread = threading.Thread(
        target=serve_metrics,
        kwargs={
            "cards_path": cards_path,
            "port": port,
            "wip_limits_path": wip_limits_path,
            "escalations": escalations,
        },
        daemon=True,
    )
    thread.start()
    # Wait for the server to be ready
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    return thread


def _fetch_metrics(port: int) -> tuple[int, str]:
    """Fetch the /metrics endpoint and return (status_code, body)."""
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=5) as response:
        return response.status, response.read().decode()


def test_scrape_serves_cycle_time_lead_time_throughput_wip_blocked_escalation(tmp_path):
    """AC1: one completed card created 6 days and started 4 days before completion,
    no WIP limits, no escalations — /metrics returns 200 with all six metric lines."""
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([COMPLETED_CARD]))

    port = 18081
    thread = _start_server(str(cards_path), port)
    try:
        status, body = _fetch_metrics(port)
        assert status == 200
        assert "sprint_cycle_time_days 4" in body
        assert "sprint_lead_time_days 6" in body
        assert "sprint_throughput_cards 1" in body
        assert "sprint_wip_violations 0" in body
        assert "sprint_blocked_aging_days 0" in body
        assert "sprint_escalation_rate_percent 0" in body
    finally:
        thread.join(timeout=5)


def test_scrape_reflects_updated_cards_file(tmp_path):
    """AC2: after the cards file is updated from one to two completed cards,
    the next /metrics request shows throughput 2."""
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([COMPLETED_CARD]))

    port = 18082
    thread = _start_server(str(cards_path), port)
    try:
        # First request: one card
        status, body = _fetch_metrics(port)
        assert status == 200
        assert "sprint_throughput_cards 1" in body

        # Update the cards file to two completed cards
        cards_path.write_text(json.dumps([COMPLETED_CARD, COMPLETED_CARD]))

        # Second request: two cards
        status, body = _fetch_metrics(port)
        assert status == 200
        assert "sprint_throughput_cards 2" in body
    finally:
        thread.join(timeout=5)


def test_scrape_reports_wip_violation(tmp_path):
    """AC3: four in-flight cards with WIP limit of 3 for In Progress —
    /metrics shows sprint_wip_violations 1."""
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([IN_FLIGHT_CARD] * 4))

    wip_path = tmp_path / "wip-limits.json"
    wip_path.write_text(json.dumps({"In Progress": 3}))

    port = 18083
    thread = _start_server(str(cards_path), port, wip_limits_path=str(wip_path))
    try:
        status, body = _fetch_metrics(port)
        assert status == 200
        assert "sprint_wip_violations 1" in body
    finally:
        thread.join(timeout=5)


def test_scrape_reports_escalation_rate(tmp_path):
    """AC4: 10 completed cards with 2 escalations — /metrics shows
    sprint_escalation_rate_percent 20."""
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps([COMPLETED_CARD] * 10))

    port = 18084
    thread = _start_server(str(cards_path), port, escalations=2)
    try:
        status, body = _fetch_metrics(port)
        assert status == 200
        assert "sprint_escalation_rate_percent 20" in body
    finally:
        thread.join(timeout=5)


def test_scrape_reports_zero_for_empty_cards_file(tmp_path):
    """AC5: empty cards file — /metrics returns 200 with all metrics at 0."""
    cards_path = tmp_path / "cards.json"
    cards_path.write_text("[]")

    port = 18085
    thread = _start_server(str(cards_path), port)
    try:
        status, body = _fetch_metrics(port)
        assert status == 200
        assert "sprint_cycle_time_days 0" in body
        assert "sprint_lead_time_days 0" in body
        assert "sprint_throughput_cards 0" in body
        assert "sprint_wip_violations 0" in body
        assert "sprint_blocked_aging_days 0" in body
        assert "sprint_escalation_rate_percent 0" in body
    finally:
        thread.join(timeout=5)
