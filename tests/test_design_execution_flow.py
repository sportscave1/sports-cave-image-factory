"""Photo limitations must never turn an authorised design into a review pause."""
import pytest

from design_execution_flow import CONTINUOUS_DESIGN_FLOW
from home_morning_brief_actions import _prompt
from home_design_refresh import _refresh_prompt
import morning_design_queue as queue

SOURCE = dict(id="id:selected", rev="r1", path_display="/Review/Collector.psd")
RECEIPT = "00000000-0000-0000-0000-000000000001"


def prompts():
    return [
        _prompt("Collector", "Create a tribute from the 21 November match."),
        _refresh_prompt(dict(title="Existing Edition", product_id="123"), "https://example.test/edition"),
        _prompt("Collector", "Keep the original photograph", edit=dict(source=SOURCE, metadata=dict(upload_intent="new_product"))),
        queue._job_prompt(RECEIPT, "Collector", "Create a tribute from the 21 November match."),
    ]


@pytest.mark.parametrize("prompt", prompts(), ids=("new", "refresh", "edit", "queued"))
def test_new_refresh_edit_and_queue_continue_with_available_images(prompt):
    assert prompt.count(CONTINUOUS_DESIGN_FLOW) == 1
    assert "The user performs photographic, licensing and collector-art suitability review manually after delivery" in prompt
    assert "Do not ask the user to supply, approve or confirm photographs" in prompt
    assert "an unavailable original or limited resolution is a source limitation to note, never a prerequisite for generation" in prompt
    assert "SC_DESIGN_BLOCKED" not in prompt
    assert "**Creative review before generation.**" not in prompt
    assert "Use the selected full-resolution originals as actual inputs" not in prompt
    assert prompt.index(CONTINUOUS_DESIGN_FLOW) < prompt.index("**1.")
    assert "matching UTF-8" in prompt and "SC_EDITION_NUMBER" in prompt


def test_old_waiting_new_job_upgrades_without_changing_brief_or_receipts():
    brief = "Create the 21 November match tribute. Preserve both players."
    current = queue._job_prompt(RECEIPT, "Collector", brief)
    legacy = current.replace(CONTINUOUS_DESIGN_FLOW, "").replace(
        "**Composition direction for the single generation.**", "**Creative review before generation.**")
    legacy += "\nQueue retry receipt: " + RECEIPT + "\n"
    legacy += "\nQueue output receipt: " + RECEIPT + "\n"
    job = dict(id=RECEIPT, title="Collector", prompt=legacy)
    upgraded = queue._waiting_prompt(job)
    assert CONTINUOUS_DESIGN_FLOW in upgraded and brief in upgraded
    assert "**Creative review before generation.**" not in upgraded
    assert queue._receipt(job) == queue._receipt(dict(job, prompt=upgraded))
    assert queue._output_key(job) == queue._output_key(dict(job, prompt=upgraded))
    assert queue._waiting_prompt(dict(job, prompt=upgraded)) == upgraded


def test_queued_edit_adds_execution_rules_without_changing_selected_revision_or_request():
    prompt = "**USER-REQUESTED DESIGN CHANGES**\nFix the spacing only.\n\n" + prompts()[2]
    legacy = prompt.replace(CONTINUOUS_DESIGN_FLOW, "")
    job = dict(id=RECEIPT, title="Collector", section="edit", prompt=legacy)
    upgraded = queue._waiting_prompt(job)
    assert upgraded == CONTINUOUS_DESIGN_FLOW + legacy
    assert '"rev": "r1"' in upgraded and "Fix the spacing only." in upgraded
    assert queue._receipt(job) == queue._receipt(dict(job, prompt=upgraded))
    assert queue._waiting_prompt(dict(job, prompt=upgraded)) == upgraded


def test_queued_refresh_keeps_edition_identity_and_exact_receipt():
    old = "SPORTS CAVE EXISTING DESIGN REFRESH\n" + prompts()[1].replace(CONTINUOUS_DESIGN_FLOW, "")
    old += '\nInclude morning_design_job_id = "' + RECEIPT + '" in the final .upload.json.\n'
    old += "\nQueue retry receipt: " + RECEIPT + "\n"
    job = dict(id=RECEIPT, title="Existing Edition", prompt=old)
    upgraded = queue._waiting_prompt(job)
    assert CONTINUOUS_DESIGN_FLOW in upgraded
    assert "Shopify product ID: 123" in upgraded
    assert "Existing edition/product title (preserve): Existing Edition" in upgraded
    assert queue._receipt(job) == queue._receipt(dict(job, prompt=upgraded))
    assert queue._waiting_prompt(dict(job, prompt=upgraded)) == upgraded


def test_unclaimed_old_edit_gets_scope_and_closeout_recovery_without_changing_brief():
    from design_review_prompt import EDIT_EXECUTION_RULES
    prompt = '**USER-REQUESTED DESIGN CHANGES**\nRemove only the score.\n\n' + prompts()[2]
    legacy = prompt.replace(EDIT_EXECUTION_RULES, '')
    job = dict(id=RECEIPT, title='Collector', section='edit', prompt=legacy)
    upgraded = queue._waiting_prompt(job)
    assert upgraded == EDIT_EXECUTION_RULES + legacy
    assert 'Remove only the score.' in upgraded and '"rev": "r1"' in upgraded
    assert queue._waiting_prompt(dict(job, prompt=upgraded)) == upgraded
    assert queue._receipt(job) == queue._receipt(dict(job, prompt=upgraded))
