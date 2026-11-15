"""Consistent, non-mutating ordering for user-facing categorical options."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
import re
from typing import Any


_NUMBER_PART = re.compile(r"(\d+)")
_PLACEHOLDER_PREFIXES = ("select", "choose")
_NONE_LABELS = frozenset({"none", "no selection"})
_ALL_LABELS = frozenset({"all", "all categories"})


def natural_label_key(label: object) -> tuple[tuple[int, object], ...]:
    """Return a case-insensitive key with numeric chunks compared numerically."""

    cleaned = str(label if label is not None else "").strip().casefold()
    return tuple(
        (1, int(part)) if part.isdigit() else (0, part)
        for part in _NUMBER_PART.split(cleaned)
        if part
    )


def _read_option_field(option: object, accessor: str | Callable[[object], object] | None, *, label: bool) -> object:
    if callable(accessor):
        return accessor(option)
    if isinstance(accessor, str):
        if isinstance(option, Mapping):
            return option.get(accessor)
        return getattr(option, accessor, None)
    if label:
        if isinstance(option, Mapping) and "label" in option:
            return option.get("label")
        if hasattr(option, "label"):
            return getattr(option, "label")
        if isinstance(option, (tuple, list)) and len(option) == 2:
            return option[0]
        return option
    if isinstance(option, Mapping):
        for field in ("value", "id", "key", "slug", "handle"):
            if field in option:
                return option.get(field)
    for field in ("value", "id", "key", "slug", "handle"):
        if hasattr(option, field):
            return getattr(option, field)
    if isinstance(option, (tuple, list)) and len(option) == 2:
        return option[1]
    return option


def _normalised_labels(labels: Iterable[object]) -> tuple[str, ...]:
    return tuple(str(label if label is not None else "").strip().casefold() for label in labels)


def alphabetize_options(
    options: Iterable[Any],
    *,
    label: str | Callable[[Any], object] | None = None,
    value: str | Callable[[Any], object] | None = None,
    first: Iterable[object] = (),
    last: Iterable[object] = (),
) -> tuple[Any, ...]:
    """Return categorical options in natural A-Z label order without changing them.

    Empty/Select/Choose placeholders are kept first, followed by an exact ``All``
    option. Exact ``None``/``No selection`` controls keep their source position.
    An exact ``Other`` catch-all remains last. Callers can pin equivalent control
    labels with ``first`` or ``last``. Equal visible labels are deterministically
    ordered by their underlying value/ID and are never de-duplicated.
    """

    indexed = list(enumerate(tuple(options)))
    first_labels = _normalised_labels(first)
    last_labels = _normalised_labels(last)

    def visible(option: Any) -> str:
        return str(_read_option_field(option, label, label=True) or "").strip()

    def identity(option: Any) -> tuple[tuple[int, object], ...]:
        return natural_label_key(_read_option_field(option, value, label=False))

    pinned = []
    sortable = []
    for source_index, option in indexed:
        if visible(option).casefold() in _NONE_LABELS:
            pinned.append((source_index, option))
        else:
            sortable.append((source_index, option))

    def option_key(item: tuple[int, Any]):
        source_index, option = item
        shown = visible(option)
        normalised = shown.casefold()
        if not normalised or any(
            normalised == prefix
            or normalised.startswith(f"{prefix} ")
            or normalised.startswith(f"{prefix}…")
            or normalised.startswith(f"{prefix}...")
            for prefix in _PLACEHOLDER_PREFIXES
        ):
            group = (0, 0)
        elif normalised in _ALL_LABELS:
            group = (1, 0)
        elif normalised in first_labels:
            group = (2, first_labels.index(normalised))
        elif normalised in last_labels:
            group = (4, last_labels.index(normalised))
        elif normalised == "other":
            group = (5, 0)
        else:
            group = (3, 0)
        return group, natural_label_key(shown), identity(option), source_index

    ordered = [option for _source_index, option in sorted(sortable, key=option_key)]
    for source_index, option in pinned:
        ordered.insert(min(source_index, len(ordered)), option)
    return tuple(ordered)


def selected_option_index(options: Iterable[Any], selected: Any, *, default: int = 0) -> int:
    """Resolve an existing stored selection after presentation-only reordering."""

    ordered = tuple(options)
    try:
        return ordered.index(selected)
    except ValueError:
        return default
