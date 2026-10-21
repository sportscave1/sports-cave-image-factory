"""Public generation acknowledgement, with no source paths or provider messages."""
import re
import uuid

CONTAINER = "sc-product-mockup-generation"
LABELS = {"idle": "Artwork ready", "working": "Generating mockups",
          "ready": "Mockups ready", "failed": "Mockup generation failed",
          "changed": "Product details changed"}


def attempt(key, name, sport, source_hash, *, job=None, reused=False, failed=False):
    return dict(receipt=uuid.uuid4().hex, key=str(key), name=name.strip(), sport=sport,
                source_hash=source_hash, job=job, reused=reused, failed=failed)


def status(value, job, applied, result, key, name, sport, source_hash):
    result_matches = bool(result and result.get("_product_upload_intake") == str(key)
                          and result.get("_product_upload_source_hash") == source_hash
                          and result.get("product_name") == name.strip()
                          and result.get("sport_category") == sport)
    if not value:
        return ("ready" if result_matches else "idle"), "0" * 32
    receipt = value["receipt"]
    if (value["key"], value["name"], value["sport"], value["source_hash"]) != (str(key), name.strip(), sport, source_hash):
        return "changed", receipt
    if value["failed"]:
        return "failed", receipt
    if value["reused"]:
        return ("ready" if result_matches else "changed"), receipt
    if not job or job["token"] != value["job"]:
        return "changed", receipt
    if job["state"] in {"Failed", "Cancelled"}:
        return "failed", receipt
    if job["state"] == "Ready" and applied == job["token"] and result_matches:
        return "ready", receipt
    return "working", receipt


def markup(state, receipt):
    if state not in LABELS or not re.fullmatch("[a-f0-9]{32}", receipt):
        raise ValueError("Invalid public generation acknowledgement.")
    # The opaque attempt ID is an HTML identity, never spoken/displayed content.
    return (f'<div id="{CONTAINER}" role="group" aria-label="Product mockup generation">'
            f'<div id="{CONTAINER}-{state}-{receipt}" role="status" '
            f'aria-label="{LABELS[state]}">{LABELS[state]}</div></div>')
