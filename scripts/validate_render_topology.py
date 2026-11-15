"""Fail closed when render.yaml could create a second Sports Cave OS app."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY_DOC = ROOT / "docs" / "RENDER_SERVICE_TOPOLOGY.md"
CANONICAL_PRIMARY_NAME = "sports-cave-os"
CANONICAL_PRIMARY_ID = "srv-d8kl4on7f7vs73dvavv0"
PRIMARY_NAMES = frozenset({"sports-cave-os", "sports-cave-image-factory"})
INTENTIONAL_SUPPORT_NAMES = frozenset(
    {
        "sports-cave-os-webhooks",
        "sports-cave-seo-worker",
        "sports-cave-seo-daily-sync",
    }
)


def parse_services(text: str) -> list[dict[str, str]]:
    services: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw_line in text.splitlines():
        service_match = re.match(r"^  - type:\s*([^#\s]+)", raw_line)
        if service_match:
            current = {"type": service_match.group(1).strip()}
            services.append(current)
            continue
        if current is None:
            continue
        field_match = re.match(r"^    ([A-Za-z][A-Za-z0-9]*):\s*(.*?)\s*$", raw_line)
        if field_match:
            current[field_match.group(1)] = field_match.group(2).strip(" '\"")
    return services


def validation_errors(services: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    primary = [
        service
        for service in services
        if service.get("name") in PRIMARY_NAMES
        or "sports_cave_server.py" in service.get("startCommand", "")
    ]
    if primary:
        names = ", ".join(service.get("name") or "<unnamed>" for service in primary)
        errors.append(
            "The canonical primary app is externally managed; render.yaml must declare zero "
            f"primary apps, but found: {names}."
        )

    webhooks = [service for service in services if service.get("name") == "sports-cave-os-webhooks"]
    if len(webhooks) != 1:
        errors.append(f"render.yaml must declare exactly one sports-cave-os-webhooks service; found {len(webhooks)}.")
    elif "webhook_server.py" not in webhooks[0].get("startCommand", ""):
        errors.append("sports-cave-os-webhooks must start webhook_server.py.")

    allowed = INTENTIONAL_SUPPORT_NAMES
    unexpected_sports_cave = [
        service.get("name") or "<unnamed>"
        for service in services
        if str(service.get("name") or "").startswith("sports-cave-")
        and service.get("name") not in allowed
    ]
    if unexpected_sports_cave:
        errors.append("Unexpected Sports Cave Render service declaration(s): " + ", ".join(unexpected_sports_cave))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=ROOT / "render.yaml")
    args = parser.parse_args(argv)
    services = parse_services(args.path.read_text(encoding="utf-8"))
    errors = validation_errors(services)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print(f"See {TOPOLOGY_DOC}")
        return 1
    print(
        "Render topology valid: canonical primary "
        f"{CANONICAL_PRIMARY_NAME} ({CANONICAL_PRIMARY_ID}) remains externally managed; "
        "Blueprint owns one webhook service."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
