"""Scrape endpoint for serving sprint metrics in Prometheus text format."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from sprint_metrics.crew_performance import (
    Card,
    _as_cards,
    calculate_blocked_aging,
    calculate_cycle_time_and_lead_time,
    calculate_escalation_rate,
    calculate_throughput,
    calculate_wip_violations,
)


def _load_cards_from_file(path: str) -> list[Card]:
    """Read and parse the cards JSON file."""
    with open(path) as f:
        source = f.read()
    raw = json.loads(source) if source.strip() else []
    if not isinstance(raw, list):
        raise TypeError("expected a JSON list of cards")
    return _as_cards(raw)


def _load_wip_limits_from_file(path: str | None) -> dict[str, int] | None:
    """Read and parse the WIP limits JSON file."""
    if path is None:
        return None
    with open(path) as f:
        source = f.read()
    raw = json.loads(source) if source.strip() else {}
    if not isinstance(raw, dict):
        raise TypeError("expected a JSON object of WIP limits, keyed by state")
    return {str(state): int(limit) for state, limit in raw.items()}


def format_metrics(
    cards: list[Card],
    wip_limits: dict[str, int] | None = None,
    escalations: int = 0,
) -> str:
    """Format sprint metrics in Prometheus text exposition format."""
    cycle_time, lead_time = calculate_cycle_time_and_lead_time(cards)
    throughput = calculate_throughput(cards)
    wip_violations = calculate_wip_violations(cards, wip_limits)
    blocked_aging = calculate_blocked_aging(cards)
    escalation_rate = calculate_escalation_rate(cards, escalations)

    lines = [
        f"sprint_cycle_time_days {cycle_time}",
        f"sprint_lead_time_days {lead_time}",
        f"sprint_throughput_cards {throughput}",
        f"sprint_wip_violations {wip_violations}",
        f"sprint_blocked_aging_days {blocked_aging}",
        f"sprint_escalation_rate_percent {escalation_rate}",
    ]
    return "\n".join(lines) + "\n"


class _MetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler that serves sprint metrics at /metrics."""

    cards_path: str
    wip_limits_path: str | None
    escalations: int

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/metrics":
            try:
                cards = _load_cards_from_file(self.cards_path)
                wip_limits = _load_wip_limits_from_file(self.wip_limits_path)
                body = format_metrics(cards, wip_limits, self.escalations)
            except (TypeError, ValueError, OSError) as exc:
                self.send_response(500)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(str(exc).encode())
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.end_headers()
            self.wfile.write(body.encode())
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not Found\n")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        pass


def serve_metrics(
    cards_path: str,
    port: int = 8080,
    wip_limits_path: str | None = None,
    escalations: int = 0,
) -> None:
    """Start an HTTP server that serves sprint metrics at /metrics.

    Blocks until interrupted (KeyboardInterrupt or SystemExit).
    """
    handler = type(
        "MetricsHandler",
        (_MetricsHandler,),
        {
            "cards_path": cards_path,
            "wip_limits_path": wip_limits_path,
            "escalations": escalations,
        },
    )
    server = HTTPServer(("", port), handler)
    try:
        server.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        server.server_close()
