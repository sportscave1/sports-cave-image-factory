"""Safe, bounded explanations for data-only recording problems."""
FRAME_NAVIGATION = "Frame navigation is unsupported; V1 records only the main frame."
CAPTURE_REASONS = {
    "modified_click": "Modified click or new-tab action is unsupported. Use a normal click in the recorded tab.",
    "rich_edit": "Canvas, drawing or rich-text action is unsupported. Record a standard labelled control instead.",
    "new_tab": "New-tab navigation is unsupported. Open the destination in the recorded tab.",
    "click_target": "The click target has no reliable label. Record a labelled button or link instead.",
    "field_target": "The field has no reliable label. Record a labelled input instead.",
    "multiple_files": "Only one file per upload control is supported. Select a single file.",
    "multiple_selection": "Multi-select controls are unsupported. Record a single-choice control instead.",
    "rich_text": "Rich-text editing is unsupported. Use a plain text field instead.",
    "enter_submit": "Enter-key submission is unsupported. Record a click on the submit button instead.",
    "shortcut": "This keyboard shortcut is unsupported. Record the equivalent labelled control instead.",
    "pointer_gesture": "Double-click, right-click or drag/drop is unsupported. Use a normal click instead.",
}

def issues(task):
    result=[]
    from urllib.parse import urlsplit, parse_qs
    import uuid
    import re
    product_upload = False
    source_bound = False
    for i, step in enumerate(task["steps"],1):
        if step["action"] in {"navigate", "wait_url"} and isinstance(step.get("value"), str):
            query = parse_qs(urlsplit(step["value"]).query)
            if query.get("page") == ["product_uploads"]:
                product_upload = True
                if step["action"] == "navigate": source_bound = False
                try:
                    uuid.UUID(query.get("upload", [""])[0])
                    source_bound = True
                except ValueError:
                    pass
            elif step["action"] == "navigate":
                product_upload = source_bound = False
        if step["action"] == "upload": source_bound = True
        loc = step.get("locator", {})
        needs_source = any(name in loc.get("value", "").lower() for name in ("generate mockups", "black frame", "copied"))
        needs_source |= loc.get("by") == "test_id" and loc.get("value", "").startswith("stBaseButton")
        if product_upload and not source_bound and needs_source:
            reason = "Product Uploads source prerequisite is missing. Record from Choose PSD, or start with the exact saved upload recovery URL (?page=product_uploads&upload=<workflow ID>). Opening the page alone cannot restore the selected PSD."
            result.append({"step":i,"kind":"prerequisite","reason":reason,"explanation":reason})
            # One actionable prerequisite warning per recording.
            product_upload = False
        if loc.get("by") == "test_id" and re.match(r"st[A-Z]", loc.get("value", "")):
            reason = "This older step uses a shared Streamlit widget identifier. Rerecord the intended named control; its identity cannot be recovered safely from this identifier."
            result.append({"step":i,"kind":"target","reason":reason,"explanation":reason})
        if step["action"]!="unsupported":continue
        reason=step["reason"]
        interrupted="interrupted before Stop" in reason or "closed before Stop" in reason
        if reason==FRAME_NAVIGATION:
            explanation="An embedded page loaded. The older recorder flagged this even without a user action. Verify the destination and add a readiness check in a copy."
        elif interrupted:
            explanation="Recording ended before Stop. Review the final intended action or record a replacement; this is an interruption, not an unsupported click."
        else:explanation=reason
        result.append({"step":i,"kind":"interrupted" if interrupted else "unsupported","reason":reason,"explanation":explanation})
    return result
