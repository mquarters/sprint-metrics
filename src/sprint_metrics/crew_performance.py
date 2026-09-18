"""Crew performance command: report cycle time and lead time for the current sprint."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Card:
    """A single card on the sprint board.

    ``started`` and ``completed`` are ``None`` while the card has not yet
    reached that point on the board.
    """

    created: date
    started: date | None = None
    completed: date | None = None

    @property
    def is_completed(self) -> bool:
        """Whether the card has finished, and so counts towards the metrics."""
        return self.completed is not None

    @property
    def cycle_time(self) -> int:
        """Days from starting work to completing it, or 0 if either is missing."""
        if self.completed is None or self.started is None:
            return 0
        return (self.completed - self.started).days

    @property
    def lead_time(self) -> int:
        """Days from creation to completion, or 0 if the card is not complete."""
        if self.completed is None:
            return 0
        return (self.completed - self.created).days


def _parse_date(value: object, field: str) -> date | None:
    """Read an optional ISO-8601 date. Missing, null and empty all mean "not yet"."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field} must be an ISO-8601 date string, got {value!r}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} is not an ISO-8601 date: {value!r}") from exc


def parse_card(raw: Mapping[str, object]) -> Card:
    """Build a ``Card`` from its serialised form."""
    created = _parse_date(raw.get("created"), "created")
    if created is None:
        raise ValueError("every card needs a 'created' date")
    return Card(
        created=created,
        started=_parse_date(raw.get("started"), "started"),
        completed=_parse_date(raw.get("completed"), "completed"),
    )


def _as_cards(cards: Iterable[Card | Mapping[str, object]]) -> list[Card]:
    """Accept cards either already parsed or still in their serialised form."""
    return [card if isinstance(card, Card) else parse_card(card) for card in cards]


def _mean_days(values: Sequence[int]) -> int:
    """Average a set of day counts, to the nearest whole day. No values means 0."""
    if not values:
        return 0
    return round(sum(values) / len(values))


def calculate_cycle_time_and_lead_time(
    cards: Iterable[Card | Mapping[str, object]],
) -> tuple[int, int]:
    """Return the sprint's average cycle time and lead time, in whole days.

    Only completed cards carry these metrics, so cards still in flight are
    ignored. A sprint with nothing completed reports 0 for both.
    """
    completed = [card for card in _as_cards(cards) if card.is_completed]
    return (
        _mean_days([card.cycle_time for card in completed]),
        _mean_days([card.lead_time for card in completed]),
    )


def format_performance_table(cards: Iterable[Card | Mapping[str, object]]) -> str:
    """Render the crew performance metrics as a markdown table."""
    cycle_time, lead_time = calculate_cycle_time_and_lead_time(cards)
    return "\n".join(
        [
            "| Sprint | Cycle time | Lead time |",
            "|--------|------------|-----------|",
            f"| Current | {cycle_time} days | {lead_time} days |",
        ]
    )


def _load_cards(source: str) -> list[Card]:
    """Parse the JSON list of cards the command was given."""
    raw = json.loads(source) if source.strip() else []
    if not isinstance(raw, list):
        raise TypeError("expected a JSON list of cards")
    return _as_cards(raw)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the crew performance command."""
    parser = argparse.ArgumentParser(
        prog="sprint-metrics",
        description="Report cycle time and lead time for the current sprint.",
    )
    parser.add_argument(
        "cards",
        nargs="?",
        type=argparse.FileType("r"),
        default=sys.stdin,
        help="JSON file of sprint cards; reads stdin when omitted.",
    )
    args = parser.parse_args(argv)

    with args.cards as handle:
        source = handle.read()

    try:
        cards = _load_cards(source)
    except (TypeError, ValueError) as exc:
        print(f"sprint-metrics: {exc}", file=sys.stderr)
        return 2

    print(format_performance_table(cards))
    return 0
