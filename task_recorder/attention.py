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
    for i, step in enumerate(task["steps"],1):
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
