"""Saved prompts for working in QuickBooks through Codex."""

import streamlit as st

import prompt_store
from activity_log import get_activity_actor
from crm_prompt_copy import copy_prompt


# These IDs are persisted by the prompt store. Keep them stable when titles change.
WEEKLY_PROMPT_ID = "accounting_update_quickbooks"
BAS_PROMPT_ID = "accounting_bas_review"
PROMPTS = (
    (
        WEEKLY_PROMPT_ID,
        "Weekly Bookkeeping",
        "Update QuickBooks, check sales and fees, categorise expenses, match payouts and reconcile statements.",
        "Review imported sales, refunds, fees and adjustments against the source records. "
        "Check GST on Australian sales and use delivery evidence to verify qualifying exports. "
        "Use receipts and verified supplier rules for expenses. Check payout components before matching "
        "settlements to deposits received into Commonwealth Bank. Investigate differences against available "
        "bank and payment-provider statements before completing reconciliations.",
    ),
    (
        "accounting_sales_gst",
        "Sales GST",
        "Check GST on Australian sales and qualifying exports.",
        "Check that taxable Australian sales include GST and qualifying overseas exports are GST-free. "
        "Verify delivery details and source records rather than relying on currency alone.",
    ),
    (
        "accounting_platform_fees",
        "Platform Fees and GST",
        "Verify fees and supported GST for each sales and payment platform.",
        "Compare Shopify, PayPal, Afterpay, eBay and Etsy fee totals against their statements and tax invoices. "
        "Record the full fees and claim only eligible GST supported by provider records. "
        "Correct any understated imported fee amount before applying its verified GST treatment.",
    ),
    (
        "accounting_match_payouts",
        "Match Payouts",
        "Match platform settlements to deposits received into Commonwealth Bank.",
        "Check the sales, refunds, fees and adjustments that make up each settlement. "
        "Match actual Commonwealth Bank deposits to existing payout records. Use the relevant clearing "
        "account and avoid duplicating sales or fees when recording the settlement.",
    ),
    (
        "accounting_categorise_expenses",
        "Categorise Expenses",
        "Use receipts and supplier rules to check expense categories and GST.",
        "Match and categorise business expenses using receipts and verified supplier rules. "
        "Separate personal spending and flag uncertain categories, GST treatment or missing evidence.",
    ),
    (
        "accounting_reconcile_accounts",
        "Reconcile Accounts",
        "Reconcile bank and payment-provider accounts against statements.",
        "Reconcile Commonwealth Bank and relevant payment-provider balances against statements. Investigate "
        "refunds, held funds, currency differences and unmatched transactions. Never force balances or create "
        "unexplained adjustments.",
    ),
    (
        BAS_PROMPT_ID,
        "Accounting Report / BAS Review",
        "Summarise completed work, GST totals and items still open for review.",
        "Use the available QuickBooks reports and supporting records to prepare the accounting report. "
        "Identify the records behind the GST figures and flag any totals that still need verification.",
    ),
)

PERIOD = (
    "Establish the relevant period from the last verified completion and the available records. "
    "State the dates you used and ask me about the period only if it remains unclear."
)
RULES = (
    "Match existing records first, avoid duplicates and preserve correct manual changes. "
    "Verify both the full fee totals and the GST charged against provider records. "
    "Ask for my explicit approval before changing lodged BAS periods or making bulk historical corrections."
)
COMPLETION = (
    "Report what you checked, what you completed and what remains open. "
    "Flag uncertain items and list any missing documents needed to resolve them."
)


def _build_prompt(prompt_id, title, instructions):
    sections = [f"QuickBooks task: {title}", PERIOD]
    if prompt_id == WEEKLY_PROMPT_ID:
        sections.append(
            "Update QuickBooks for the period. Check sales and fees, categorise expenses, match payouts "
            "and reconcile accounts against available statements."
        )
    sections.extend((instructions.strip(), RULES, COMPLETION))
    if prompt_id == BAS_PROMPT_ID:
        sections.append(
            "Include GST collected, eligible GST credits, outstanding differences and missing documents "
            "in the report. Do not lodge the BAS."
        )
    return "\n\n".join(sections)


def _render_card(prompt_id, title, description, saved):
    with st.container(border=True):
        details, actions = st.columns([3, 1], vertical_alignment="center")
        details.subheader(title)
        details.caption(description)

        with st.expander("View or edit prompt"):
            with st.form(f"{prompt_id}_form", border=False):
                draft = st.text_area("Prompt instructions", value=saved, height=110)
                submitted = st.form_submit_button("Save prompt")
            if submitted:
                if not draft.strip():
                    st.warning("Enter prompt instructions before saving.")
                else:
                    try:
                        record = prompt_store.save_prompt(
                            prompt_id, title, draft, module="accounting", updated_by=get_activity_actor()
                        )
                    except RuntimeError:
                        st.error("The prompt could not be saved. Try again.")
                    else:
                        saved = record["text"]
                        if record["warning"]:
                            st.warning(record["warning"])
                        else:
                            st.success("Prompt saved.")

            prompt = _build_prompt(prompt_id, title, saved)
            st.caption("Copied text")
            st.code(prompt, language=None, wrap_lines=True)

        with actions:
            copy_prompt(prompt, f"{prompt_id}_copy", label="Copy")


def render_page():
    st.title("Accounting")
    st.caption("Copy a saved prompt into Codex to work in QuickBooks.")
    specs = [
        {"prompt_key": prompt_id, "prompt_name": title, "default_text": instructions}
        for prompt_id, title, _, instructions in PROMPTS
    ]
    records = prompt_store.load_prompt_records(specs, module="accounting")
    if any(record["warning"] for record in records.values()):
        st.warning("Saved prompts could not be loaded. The default text is available to copy.")

    (weekly_id, weekly_title, weekly_description, _), *other_prompts = PROMPTS
    _render_card(weekly_id, weekly_title, weekly_description, records[weekly_id]["text"])
    for first in range(0, len(other_prompts), 2):
        for column, (prompt_id, title, description, _) in zip(st.columns(2), other_prompts[first : first + 2]):
            with column:
                _render_card(prompt_id, title, description, records[prompt_id]["text"])
