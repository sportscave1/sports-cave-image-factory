"""Editable Codex prompts for manual QuickBooks reviews."""

from datetime import date

import streamlit as st

import prompt_store
import supabase_backend
from activity_log import get_activity_actor
from crm_prompt_copy import copy_prompt


PROMPTS = (
    (
        "update_quickbooks",
        "Update QuickBooks",
        "Review transactions since the last completed update. Check imported sales, refunds, fees "
        "and payouts. Match existing records first, avoid duplicates and preserve correct manual changes.",
    ),
    (
        "sales_gst",
        "Check Sales GST",
        "Check that taxable Australian sales include 10% GST and qualifying overseas exports are GST-free. "
        "Verify delivery details and source records rather than relying on currency alone.",
    ),
    (
        "platform_fees",
        "Check Platform Fees and GST",
        "Compare Shopify, PayPal, Afterpay, eBay and Etsy fees against their statements and tax invoices. "
        "Record the full fees and claim eligible GST actually charged. Check both the fee totals and GST. "
        "Correct any understated imported fee amount before applying its verified GST treatment.",
    ),
    (
        "match_payouts",
        "Match Payouts",
        "In QuickBooks Integration transactions, check the sales, refunds, fees and adjustments before "
        "confirming each payout. Match deposits actually received into Commonwealth Bank to existing payout "
        "records. Keep clearing accounts working correctly and never count payouts as additional sales.",
    ),
    (
        "categorise_expenses",
        "Categorise Expenses",
        "Match and categorise business expenses using receipts and verified supplier rules. Apply supported "
        "GST treatment, separate personal spending and flag missing evidence.",
    ),
    (
        "reconcile_accounts",
        "Reconcile Accounts",
        "Reconcile Commonwealth Bank and relevant payment-provider balances against statements. Investigate "
        "refunds, held funds, currency differences and unmatched transactions. Never force balances or create "
        "unexplained adjustments.",
    ),
    (
        "bas_review",
        "Prepare BAS Review",
        "Summarise GST collected, eligible GST credits and unresolved discrepancies for review.",
    ),
)

DOCUMENTS = (
    "Platform transaction and payout reports",
    "Fee tax invoices",
    "Bank statements",
    "Expense receipts",
)

REVIEW_SETTING = "accounting_last_completed_review"
APPROVAL = "Ask for my explicit approval before changing any lodged BAS period or making bulk historical corrections."
COMPLETION = (
    "Provide a short completion report covering what you checked, what you changed, and what remains open. "
    "Flag uncertain items and missing evidence for review."
)


def _build_prompt(key, title, instructions, period, last_review):
    start, end = period
    context = f"QuickBooks task: {title}\nReview period: {start:%d %b %Y} to {end:%d %b %Y} (inclusive)"
    if key == "update_quickbooks" and last_review:
        context += f"\nLast completed review: {last_review:%d %b %Y}"
    approval = APPROVAL
    if key == "bas_review":
        approval = f"Do not lodge the BAS. {approval}"
    return "\n\n".join((context, instructions.strip(), approval, COMPLETION))


def _render_review():
    st.subheader("Last completed review")
    try:
        review = supabase_backend.get_app_setting(REVIEW_SETTING, {}, ensure_schema_first=False)
        last_review = date.fromisoformat(review["date"]) if review.get("date") else None
        saved_notes = review.get("notes", "")
    except Exception:
        st.warning("The saved review could not be loaded. Try again before editing it.")
        return None

    with st.form("accounting_review_form", border=False):
        review_date = st.date_input("Completed date", value=last_review, format="DD/MM/YYYY")
        notes = st.text_area("Review notes", value=saved_notes, height=90)
        submitted = st.form_submit_button("Save review")

    if submitted:
        if review_date is None:
            st.warning("Choose the completed review date.")
        else:
            try:
                supabase_backend.set_app_setting(
                    REVIEW_SETTING,
                    {"date": review_date.isoformat(), "notes": notes.strip()},
                    ensure_schema_first=False,
                )
            except Exception:
                st.error("The review could not be saved. Try again.")
            else:
                last_review = review_date
                st.success("Review saved.")
    return last_review


def _render_card(key, title, saved, period, last_review):
    st.subheader(title)
    copy_slot = st.empty()
    with st.expander("View prompt"):
        with st.form(f"accounting_prompt_form_{key}", border=False):
            draft = st.text_area("Prompt instructions", value=saved, height=110)
            submitted = st.form_submit_button("Save prompt")
        if submitted:
            if not draft.strip():
                st.warning("Enter prompt instructions before saving.")
            else:
                try:
                    record = prompt_store.save_prompt(
                        f"accounting_{key}", title, draft, module="accounting", updated_by=get_activity_actor()
                    )
                except RuntimeError:
                    st.error("The prompt could not be saved. Try again.")
                else:
                    saved = record["text"]
                    if record["warning"]:
                        st.warning(record["warning"])
                    else:
                        st.success("Prompt saved.")

        prompt = _build_prompt(key, title, saved, period, last_review) if len(period) == 2 else ""
        if prompt:
            st.caption("Copied text")
            st.code(prompt, language=None, wrap_lines=True)

    with copy_slot.container():
        copy_prompt(prompt, f"accounting_copy_{key}", label="Copy")


def render_page():
    st.title("Accounting")
    st.caption("Copy a saved prompt into Codex to work in QuickBooks.")
    period = st.date_input("Review period", value=(), format="DD/MM/YYYY")
    if len(period) != 2:
        st.caption("Choose a start and end date to enable Copy.")

    documents_col, review_col = st.columns(2)
    with documents_col:
        st.subheader("Documents needed")
        for index, label in enumerate(DOCUMENTS):
            st.checkbox(label, key=f"accounting_document_{index}")
    with review_col:
        last_review = _render_review()

    st.subheader("Saved prompts")
    specs = [
        {"prompt_key": f"accounting_{key}", "prompt_name": title, "default_text": instructions}
        for key, title, instructions in PROMPTS
    ]
    records = prompt_store.load_prompt_records(specs, module="accounting")
    if any(record["warning"] for record in records.values()):
        st.warning("Saved prompts could not be loaded. The default text is available to copy.")

    for first in range(0, len(PROMPTS), 2):
        for column, (key, title, _) in zip(st.columns(2), PROMPTS[first : first + 2]):
            with column.container(border=True):
                _render_card(key, title, records[f"accounting_{key}"]["text"], period, last_review)
