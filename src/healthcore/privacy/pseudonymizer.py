"""Reversible, in-memory placeholder map.

Real values are swapped for stable placeholders like [PROVIDER_1] before text leaves the device,
and swapped back locally afterwards. The map exists only in memory: it is never written to disk,
printed, or logged.
"""
import re
from dataclasses import dataclass, field

PLACEHOLDER_PATTERN = re.compile(r"\[([A-Z][A-Z_]*)_(\d+)\]")
MIN_GUARDED_LENGTH = 3  # ignore tiny strings when guarding, or common words would block everything


@dataclass
class _Entry:
    kind: str
    display: str  # what the placeholder turns back into
    matches: set[str] = field(default_factory=set)  # every spelling that gets replaced


class Pseudonymizer:
    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}  # placeholder -> entry
        self._by_value: dict[tuple[str, str], str] = {}  # (kind, display) -> placeholder
        self._counts: dict[str, int] = {}
        self._blocked: set[str] = set()

    def register(self, kind: str, display: str, matches: tuple[str, ...] = ()) -> str:
        """Return the placeholder for a value, creating it if new. `display` is what the
        placeholder restores to; `matches` are extra spellings that also get replaced."""
        key = (kind, display)
        placeholder = self._by_value.get(key)
        if placeholder is None:
            number = self._counts.get(kind, 0) + 1
            self._counts[kind] = number
            placeholder = f"[{kind}_{number}]"
            self._by_value[key] = placeholder
            self._entries[placeholder] = _Entry(kind=kind, display=display)
        self._entries[placeholder].matches.update(s for s in (display, *matches) if s)
        return placeholder

    def block(self, *values: str) -> None:
        """Values that must never appear in outbound text, even though they have no placeholder."""
        self._blocked.update(value for value in values if value)

    def sensitive_values(self) -> set[str]:
        values = set(self._blocked)
        for entry in self._entries.values():
            values |= entry.matches
        return {value for value in values if len(value) >= MIN_GUARDED_LENGTH}

    def counts(self) -> dict[str, int]:
        """How many distinct values were replaced, per kind. Never includes the values."""
        return dict(self._counts)

    def apply(self, text: str) -> str:
        """Replace every known value (any spelling, any case, whole words only) with its placeholder."""
        lookup = {
            spelling.casefold(): placeholder
            for placeholder, entry in self._entries.items()
            for spelling in entry.matches
        }
        if not lookup:
            return text
        spellings = sorted(lookup, key=len, reverse=True)  # longest first
        pattern = re.compile(
            r"(?<!\w)(?:" + "|".join(re.escape(s) for s in spellings) + r")(?!\w)",
            re.IGNORECASE,
        )
        return pattern.sub(lambda match: lookup[match.group(0).casefold()], text)

    def restore(self, text: str) -> str:
        """Put real values back. Placeholders we don't know are left untouched."""

        def swap(match: re.Match[str]) -> str:
            entry = self._entries.get(match.group(0))
            return entry.display if entry else match.group(0)

        return PLACEHOLDER_PATTERN.sub(swap, text)

    def unknown_placeholders(self, text: str) -> list[str]:
        found = {m.group(0) for m in PLACEHOLDER_PATTERN.finditer(text)}
        return sorted(found - set(self._entries))
