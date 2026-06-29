import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from certificate_logging import (
    certificate_stage,
    certificate_stage_log,
    reset_certificate_log_context,
    set_certificate_log_context,
)


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CERTIFICATE_JOB_TIMEOUT_SECONDS = 120


def certificate_job_timeout_seconds(default=DEFAULT_CERTIFICATE_JOB_TIMEOUT_SECONDS):
    try:
        return max(int(os.getenv("CERTIFICATE_JOB_TIMEOUT_SECONDS", str(default))), 1)
    except (TypeError, ValueError):
        return default


def _order_name_from_row(row):
    row = row or {}
    return (
        row.get("order")
        or row.get("order_name")
        or row.get("shopify_order_name")
        or row.get("shopify_order_number")
        or ""
    )


def _normalise_certificate_row(row):
    row = dict(row or {})
    order_name = _order_name_from_row(row)
    handle = row.get("handle") or row.get("product_handle") or row.get("shopify_handle") or ""
    return {
        **row,
        "order": order_name,
        "order_name": order_name,
        "shopify_order_name": row.get("shopify_order_name") or order_name,
        "customer": row.get("customer") or row.get("customer_name") or "",
        "customer_name": row.get("customer_name") or row.get("customer") or "",
        "customer_email": row.get("customer_email") or "",
        "product": row.get("product") or row.get("product_title") or "",
        "product_title": row.get("product_title") or row.get("product") or "",
        "handle": handle,
        "product_handle": handle,
        "shopify_handle": row.get("shopify_handle") or handle,
        "variant": row.get("variant") or row.get("variant_title") or row.get("shopify_variant_title") or "",
        "variant_title": row.get("variant_title") or row.get("shopify_variant_title") or row.get("variant") or "",
        "shopify_order_id": row.get("shopify_order_id") or row.get("order_gid") or "",
        "shopify_line_item_id": row.get("shopify_line_item_id") or row.get("line_item_id") or "",
        "shopify_product_id": row.get("shopify_product_id") or "",
        "shopify_variant_id": row.get("shopify_variant_id") or row.get("variant_id") or "",
        "variant_id": row.get("variant_id") or row.get("shopify_variant_id") or "",
        "line_item_unit_index": row.get("line_item_unit_index") or row.get("edition_offset") or 1,
        "processed_at": row.get("processed_at") or row.get("date") or row.get("purchase_date") or "",
        "date": row.get("date") or row.get("processed_at") or row.get("purchase_date") or "",
        "certificate_pdf_path": row.get("certificate_pdf_path") or row.get("local_pdf_path") or "",
        "certificate_pdf_url": row.get("certificate_pdf_url") or row.get("shopify_file_url") or row.get("pdf_url") or "",
        "certificate_shopify_file_id": row.get("certificate_shopify_file_id") or row.get("pdf_shopify_file_id") or "",
        "certificate_generated_at": row.get("certificate_generated_at") or row.get("generated_at") or "",
    }


def _certificate_context(row, source_page):
    normalised = _normalise_certificate_row(row)
    return {
        "source_page": source_page,
        "order_name": normalised.get("order_name") or "",
        "edition_order_id": normalised.get("edition_order_id") or "",
    }


def _result_error(message, *, last_stage="", source_page="", row=None):
    return {
        "ok": False,
        "error": str(message),
        "last_stage": last_stage,
        "source_page": source_page,
        "order_name": _order_name_from_row(row),
        "edition_order_id": (row or {}).get("edition_order_id") or "",
    }


def _public_certificate_record(record):
    record = dict(record or {})
    return {
        key: record.get(key)
        for key in (
            "certificate_id",
            "status",
            "local_pdf_path",
            "pdf_url",
            "certificate_pdf_url",
            "pdf_shopify_file_id",
            "shopify_pdf_file_id",
            "shopify_file_status",
            "generated_at",
            "sync_error",
            "preview_path",
            "certificate_file_url",
            "shopify_file_url",
        )
        if record.get(key) not in (None, "")
    }


def _parse_json_line(line):
    try:
        return json.loads(str(line or "").strip())
    except Exception:
        return {}


def _reader_thread(process, output_queue):
    for line in process.stdout or []:
        output_queue.put(line)


def _run_worker_command(command, *, timeout_seconds, source_page="", row=None):
    started_at = time.perf_counter()
    output_queue = queue.Queue()
    lines = []
    last_stage = "certificate_action_started"
    result = {}
    process = subprocess.Popen(
        command,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    reader = threading.Thread(target=_reader_thread, args=(process, output_queue), daemon=True)
    reader.start()
    try:
        while True:
            while True:
                try:
                    line = output_queue.get_nowait()
                except queue.Empty:
                    break
                lines.append(line)
                print(line, end="", flush=True)
                payload = _parse_json_line(line)
                if payload.get("event") == "certificate_stage" and payload.get("stage"):
                    last_stage = payload.get("stage")
                elif payload.get("event") == "certificate_result":
                    result = payload

            if process.poll() is not None:
                break
            if time.perf_counter() - started_at > timeout_seconds:
                process.kill()
                try:
                    process.wait(timeout=5)
                except Exception:
                    pass
                while True:
                    try:
                        line = output_queue.get_nowait()
                    except queue.Empty:
                        break
                    lines.append(line)
                    print(line, end="", flush=True)
                message = f"certificate job timed out at {last_stage}. You can retry this order."
                certificate_stage_log(
                    "certificate_action_finished",
                    "failed",
                    source_page=source_page,
                    order_name=_order_name_from_row(row),
                    edition_order_id=(row or {}).get("edition_order_id") or "",
                    timeout_seconds=timeout_seconds,
                    error=message,
                )
                return _result_error(message, last_stage=last_stage, source_page=source_page, row=row)
            time.sleep(0.05)

        reader.join(timeout=1)
        while True:
            try:
                line = output_queue.get_nowait()
            except queue.Empty:
                break
            lines.append(line)
            print(line, end="", flush=True)
            payload = _parse_json_line(line)
            if payload.get("event") == "certificate_stage" and payload.get("stage"):
                last_stage = payload.get("stage")
            elif payload.get("event") == "certificate_result":
                result = payload
    finally:
        if process.poll() is None:
            process.kill()
        try:
            if process.stdout:
                process.stdout.close()
        except Exception:
            pass

    if process.returncode != 0:
        message = (result.get("error") if result else "") or f"certificate worker exited with code {process.returncode}"
        return _result_error(message, last_stage=last_stage, source_page=source_page, row=row)
    if result:
        return result
    return _result_error("certificate worker did not return a result", last_stage=last_stage, source_page=source_page, row=row)


def run_certificate_job_with_timeout(row, *, source_page="Orders", upload=True, force=False, timeout_seconds=None):
    timeout_seconds = timeout_seconds or certificate_job_timeout_seconds()
    normalised = _normalise_certificate_row(row)
    token = set_certificate_log_context(**_certificate_context(normalised, source_page))
    try:
        certificate_stage_log(
            "certificate_action_started",
            "started",
            timeout_seconds=timeout_seconds,
        )
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            json.dump(normalised, handle, default=str)
            row_path = handle.name
        command = [
            sys.executable,
            "-u",
            str(BASE_DIR / "scripts" / "diagnose_certificate_generation.py"),
            "--as-worker",
            "--row-json-file",
            row_path,
            "--source-page",
            source_page,
        ]
        if upload:
            command.append("--upload")
        if force:
            command.append("--force")
        result = _run_worker_command(
            command,
            timeout_seconds=timeout_seconds,
            source_page=source_page,
            row=normalised,
        )
        return result
    finally:
        reset_certificate_log_context(token)
        try:
            if "row_path" in locals():
                Path(row_path).unlink(missing_ok=True)
        except Exception:
            pass


def _validate_row(row):
    if not row:
        raise ValueError("Selected row was not found.")
    if not _order_name_from_row(row) and not row.get("shopify_order_id"):
        raise ValueError("Selected order row is missing its order identity.")
    if not row.get("edition_number"):
        raise ValueError("This row still needs an edition number before a certificate can be generated.")
    if not row.get("edition_order_id"):
        raise ValueError("This row is missing its Supabase edition record. Ask a developer to repair missing editions first.")


def _existing_uploaded_certificate(row, config):
    import certificate_engine

    record = certificate_engine.certificate_record_from_order_row(row)
    state = certificate_engine.read_order_certificate_state(row.get("shopify_order_id"), config=config)
    existing = certificate_engine.find_existing_certificate(state.get("certificates") or [], record)
    if existing and (existing.get("pdf_url") or existing.get("certificate_url") or existing.get("certificate_pdf_url")):
        return existing
    return {}


def run_certificate_job(row, *, source_page="Diagnostic", upload=False, force=False):
    import certificate_engine
    import shopify_sync
    import supabase_backend

    normalised = _normalise_certificate_row(row)
    set_certificate_log_context(**_certificate_context(normalised, source_page))
    with certificate_stage("certificate_action_started"):
        _validate_row(normalised)
        certificate_stage_log("selected_row_validated", "completed")
        config = shopify_sync.get_config()
        if upload and not config.get("configured"):
            raise RuntimeError("Store connection is not configured for certificate upload.")

        generated_path = ""
        if normalised.get("edition_order_id"):
            generated_path = supabase_backend.generate_certificate_for_edition_order(
                normalised.get("edition_order_id"),
                force=force,
                source_page=source_page,
            )
            generated_path = str(generated_path or "").strip()
            if generated_path and Path(generated_path).exists():
                normalised["certificate_pdf_path"] = generated_path
            elif generated_path.startswith(("http://", "https://")):
                normalised["certificate_pdf_url"] = generated_path

        record = certificate_engine.certificate_record_from_order_row(normalised)
        if not upload:
            return {
                "ok": True,
                "uploaded": False,
                "generated_path": generated_path,
                "record": _public_certificate_record(record),
            }

        existing = _existing_uploaded_certificate(normalised, config)
        if existing and not force:
            return {
                "ok": True,
                "uploaded": False,
                "skipped_existing": True,
                "metafields_synced": True,
                "record": _public_certificate_record({**record, **existing, "status": "Ready"}),
            }

        record["local_pdf_path"] = normalised.get("certificate_pdf_path") or record.get("local_pdf_path") or ""
        if not str(record.get("local_pdf_path") or "").strip():
            record = certificate_engine.generate_local_certificate_for_record(record)
        if not str(record.get("local_pdf_path") or "").strip():
            raise RuntimeError(record.get("sync_error") or "Certificate PDF was not generated.")
        uploaded = certificate_engine.upload_generated_certificate_record(record, config=config)
        saved = certificate_engine.save_certificate_record_to_order(uploaded, config=config)
        if saved.get("metafields_synced") is False:
            raise RuntimeError(saved.get("metafield_error") or "Certificate uploaded, but Shopify certificate mirror failed. Retry.")
        return {
            "ok": True,
            "uploaded": True,
            "saved": bool(saved.get("saved")),
            "metafields_synced": bool(saved.get("metafields_synced")),
            "record": _public_certificate_record(saved.get("record") or uploaded),
        }
