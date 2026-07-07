import csv
import html
import io
import json
import re
import time
from datetime import datetime, timezone

import streamlit as st
import streamlit.components.v1 as components

import supabase_backend


COUNTRY_RULES = {
    "Australia": "Direct, proud, man cave, clubroom, legacy, motorsport/cricket/footy nostalgia where relevant. Use Aussie icon, built proper, clubroom ready, man cave ready, for the fans who remember, no reprints, numbered run. Avoid sounding too American.",
    "USA": "Sports den, home bar, fan cave, legacy, rivalry, greatness, collector ownership. Use fan cave, sports den, home bar, legacy, rivalry, real fans remember, numbered release.",
    "UK": "Club loyalty, terrace memory, proper football culture, understated scarcity, heritage. Use for the loyal ones, proper football walls, matchday memory, clubroom, framed history. Avoid American phrases unless chosen.",
    "Canada": "Collector room, hockey memory, sporting pride, clean but emotional. Use real fans remember, built for the wall, framed sporting history. Avoid USA-only language.",
    "New Zealand": "Proud, understated, sport identity, legacy, rugby/cricket/motorsport. Use for real fans, sporting history, clubroom ready. Avoid too much Aussie language unless relevant.",
    "Universal": "Nostalgic, collector-driven, short, emotional, premium. Use only if country is unclear.",
}

AD_FORMAT_RULES = {
    "Manual Carousel Upload": "Generate 5 manual carousel cards. Cards are micro-hooks, not paragraphs. Each card must create a different buying reason.",
    "Instant Experience + Catalogue": "Generate feed hero/banner copy, Instant Experience sections, catalogue intro, product set copy, and visual rules for one banner plus catalogue attached.",
    "Retargeting": "Generate shorter warm retargeting copy with proof, reminder, and supported urgency. Do not sound creepy.",
    "Final Scarcity": "Generate premium late-stage urgency only if the edition stage supports it. No fake countdowns.",
    "Full Launch Pack": "Generate the complete launch set: cold, warm, carousel, instant experience, retargeting, final scarcity, headlines, descriptions, and QA.",
}

FUNNEL_RULES = {
    "Cold Prospecting": "Lead with product story, sport identity, nostalgia, rivalry, or hero moment. Scarcity is secondary. Do not overdo buy-now pressure.",
    "Warm Prospecting": "Use proof, ownership, edition stage, fan identity, and a stronger CTA.",
    "Retargeting Product Viewers": "Remind them of the product or moment carefully. Mention the run is moving only if true. Keep copy short.",
    "Add To Cart Retargeting": "Use stronger urgency. Mention sellout risk only when the edition stage supports it. Reassure with framed/unframed and secure checkout if relevant.",
    "Past Customers": "Use collector ownership and next-piece language. Avoid discount-first copy.",
    "Gift Buyers": "Use the gift angle only because it was selected. Avoid generic great gift language.",
    "Final Editions": "Use true late-stage urgency. Keep it premium, not cheap.",
    "Sold Out / Archive Proof": "Do not sell unavailable product. Use it as brand proof and point toward related live drops if links exist.",
}

ANGLE_RULES = {
    "Nostalgia": "Use history, framed; captured forever; final bow; centre court silence; the moment lives; the memory never left; for the fans who remember; a piece of the era.",
    "Identity": "Use fan pride, real fans remember, club colours, wall pride, the wall says who you follow, not for casuals.",
    "Collector Value": "Use numbered run, collector piece, limited run, built to be claimed, one of 100, ownership not decoration.",
    "Australian / Man Cave / Clubroom": "Use man cave ready, clubroom ready, Aussie icon, built proper, made for real fans, built for the shed, bar, or clubroom.",
    "Scarcity": "Use once they are gone, strictly limited, final editions, no reprints, once it closes it is archived, do not wait too long.",
    "Rivalry / Debate": "Use the debate lives, two names one wall, the argument never ends, built for fans who still argue it, legacy vs legacy.",
    "Hero Moment": "Use the moment lives, one moment one memory, captured at its peak, when the sport stood still, the day fans never forgot.",
    "Gift Buyer": "Use for the fan who has everything, the piece they would never buy for themselves, give them the wall moment.",
    "Room Upgrade": "Use built for the wall that matters, man cave ready, clubroom ready, home bar ready, office wall with a story.",
    "Final Editions": "Use almost archived, final stretch, once this closes it is gone, late-stage run, final call.",
}

ANGLE_OPTIONS = list(ANGLE_RULES)
COUNTRY_OPTIONS = list(COUNTRY_RULES)
AD_FORMAT_OPTIONS = list(AD_FORMAT_RULES)
FUNNEL_OPTIONS = list(FUNNEL_RULES)
EDITION_STAGE_OPTIONS = [
    "Low Number Rush",
    "Early Run",
    "Momentum Building",
    "Halfway Mark",
    "Demand Building",
    "Running Hot",
    "Late Stage",
    "Near The End",
    "Closing Fast",
    "Final Call",
    "Archived",
    "Generic / Unknown",
]

HARD_AVOID = [
    "Premium Display",
    "High Quality Art",
    "Best Poster",
    "Shop Now",
    "Great Gift",
    "Elevate",
    "Transform",
    "Ultimate",
    "Perfect addition",
    "Poster",
    "Wall decor",
    "Home decor",
    "Stunning",
    "Beautiful artwork",
    "Cheap discount language",
    "Fake urgency",
]

QUALITY_CHECKS = [
    "Does every carousel headline fit on mobile?",
    "Does every description fit on mobile?",
    "Does each card create a different buying reason?",
    "Does copy feel like collector art, not a poster?",
    "Is nostalgia or identity clear early?",
    "Is scarcity clear by final card?",
    "Would the target country understand the tone?",
    "Is anything too generic, too long, too polished, or AI-sounding?",
    "Is there a clear CTA?",
    "Does it match the true fan base?",
    "Is every scarcity claim true?",
    "Does the ad avoid repeating the same message already visible on the product page?",
    "Does the ad lead with story for cold traffic and urgency for warm traffic?",
    "If exact edition number is used, is there a process to update the ad when numbers move?",
    "Is there no cheap discount language?",
    "Is the artwork treated as collector history, not generic wall art?",
]


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _int(value, default=0):
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _num(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _money(value):
    return f"${_num(value):,.2f}"


def _ratio(value):
    return f"{_num(value):.2f}x"


def _pct(value):
    return f"{_num(value):.2f}%"


def _safe_key(value):
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip())[:80] or "item"


def _plain_text(value, fallback=""):
    return str(value or fallback or "").strip()


def _json_default(value):
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return str(value)


def _copy_button(text, key, label="Copy"):
    text_json = json.dumps(str(text or ""))
    safe_label = html.escape(label)
    safe_key = _safe_key(key)
    components.html(
        f"""
        <style>
        .mf-copy-button {{
            width: 100%;
            border: 1px solid #babfc3;
            border-radius: 6px;
            padding: 8px 12px;
            background: #ffffff;
            color: #202223;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            box-sizing: border-box;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }}
        .mf-copy-button:hover {{
            background: #f6f6f7;
        }}
        </style>
        <button id="mf-copy-{safe_key}" class="mf-copy-button">{safe_label}</button>
        <script>
        (() => {{
          const button = document.getElementById("mf-copy-{safe_key}");
          const original = button.innerText;
          const value = {text_json};
          async function copyValue(event) {{
            event.preventDefault();
            try {{
              if (navigator.clipboard && window.isSecureContext) {{
                await navigator.clipboard.writeText(value);
              }} else {{
                const textarea = document.createElement("textarea");
                textarea.value = value;
                textarea.style.position = "fixed";
                textarea.style.opacity = "0";
                document.body.appendChild(textarea);
                textarea.focus();
                textarea.select();
                document.execCommand("copy");
                document.body.removeChild(textarea);
              }}
              button.innerText = "Copied";
              setTimeout(() => {{ button.innerText = original; }}, 1400);
            }} catch (error) {{
              button.innerText = "Copy failed";
              setTimeout(() => {{ button.innerText = original; }}, 1600);
            }}
          }}
          button.addEventListener("click", copyValue);
        }})();
        </script>
        """,
        height=44,
    )


def _inject_styles():
    st.markdown(
        """
        <style>
        .mf-header {
            background: #ffffff;
            border: 1px solid #e3e5e8;
            border-radius: 8px;
            padding: 18px 20px;
            margin-bottom: 14px;
        }
        .mf-header h1 {
            margin: 0 0 4px 0;
            color: #202223;
            font-size: 1.8rem;
            letter-spacing: 0;
        }
        .mf-header p {
            margin: 0;
            color: #616161;
            font-size: 0.95rem;
        }
        .mf-chip-row {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin: 8px 0 16px 0;
        }
        .mf-chip {
            background: #f6f6f7;
            border: 1px solid #dfe3e8;
            border-radius: 999px;
            color: #202223;
            font-size: 0.82rem;
            padding: 5px 10px;
            line-height: 1.2;
        }
        .mf-chip strong {
            font-weight: 700;
        }
        .mf-muted {
            color: #6d7175;
            font-size: 0.9rem;
        }
        .mf-copy-button {
            width: 100%;
            border: 1px solid #babfc3;
            border-radius: 6px;
            padding: 8px 12px;
            background: #ffffff;
            color: #202223;
            font-weight: 600;
            font-size: 0.9rem;
            cursor: pointer;
            box-sizing: border-box;
        }
        .mf-copy-button:hover {
            background: #f6f6f7;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: #dfe3e8 !important;
            border-radius: 8px !important;
            background: #ffffff !important;
        }
        div[data-testid="stExpander"] {
            border: 1px solid #dfe3e8 !important;
            border-radius: 8px !important;
            background: #ffffff !important;
        }
        div[data-testid="stTabs"] button {
            border-radius: 6px 6px 0 0 !important;
            color: #202223 !important;
            letter-spacing: 0 !important;
        }
        div[data-testid="stTabs"] button[aria-selected="true"] {
            border-bottom: 2px solid #b98900 !important;
            color: #202223 !important;
            background: #ffffff !important;
        }
        div[data-testid="stTextArea"] textarea {
            border-radius: 6px !important;
            border-color: #c9cccf !important;
            font-size: 0.92rem !important;
            line-height: 1.45 !important;
        }
        div[data-testid="stButton"] button[kind="primary"] {
            background: #202223 !important;
            border-color: #202223 !important;
            color: #ffffff !important;
            border-radius: 6px !important;
        }
        div[data-testid="stButton"] button,
        div[data-testid="stDownloadButton"] button {
            border-radius: 6px !important;
            font-weight: 600 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _card(title, helper=""):
    container = st.container(border=True)
    container.markdown(f"**{title}**")
    if helper:
        container.caption(helper)
    return container


@st.cache_data(ttl=180, show_spinner=False)
def _load_product_options(search="", limit=150):
    if not supabase_backend.is_configured():
        return []
    try:
        if hasattr(supabase_backend, "list_marketing_factory_product_options"):
            return supabase_backend.list_marketing_factory_product_options(search=search, limit=limit)
        if hasattr(supabase_backend, "list_edition_products_read_only"):
            return supabase_backend.list_edition_products_read_only(search=search, limit=limit)
        return supabase_backend.list_edition_products(search=search, limit=limit)
    except Exception:
        return []


@st.cache_data(ttl=180, show_spinner=False)
def _load_meta_summary(date_range="last_30_days"):
    if not supabase_backend.is_configured():
        return {"insights": [], "mapping": [], "opportunities": [], "actions": []}
    try:
        insights = supabase_backend.list_meta_ad_insights(date_range=date_range, limit=1000)
    except Exception:
        insights = []
    try:
        mapping = supabase_backend.list_ads_product_mapping_status(date_range=date_range, limit=500)
    except Exception:
        mapping = []
    try:
        opportunities = supabase_backend.list_product_opportunities_from_ads(date_range=date_range)
    except Exception:
        opportunities = []
    try:
        actions = supabase_backend.list_ads_action_log(limit=40)
    except Exception:
        actions = []
    return {"insights": insights, "mapping": mapping, "opportunities": opportunities, "actions": actions}


@st.cache_data(ttl=180, show_spinner=False)
def _load_saved_packs(limit=50):
    if not supabase_backend.is_configured():
        return []
    try:
        return supabase_backend.list_ads_copy_packs(limit=limit)
    except Exception:
        return []


def _product_handle(row):
    return _plain_text(row.get("shopify_handle") or row.get("handle") or row.get("product_handle"))


def _product_title(row):
    return _plain_text(row.get("product_title") or row.get("title") or row.get("product_handle"), "Manual product")


def _product_id(row):
    return _plain_text(row.get("shopify_product_id") or row.get("shopify_product_gid") or row.get("id"))


def _remaining(row):
    for key in ("remaining_count", "remaining_editions", "edition_remaining"):
        if row.get(key) not in (None, ""):
            return _int(row.get(key), 0)
    total = _int(row.get("edition_total") or row.get("run_edition_total"), 100)
    next_number = _int(row.get("next_edition_number") or row.get("run_next_edition_number"), 1)
    return max(total - next_number + 1, 0)


def _edition_total(row):
    return _int(row.get("edition_total") or row.get("run_edition_total"), 100)


def _next_number(row):
    return _int(row.get("next_edition_number") or row.get("run_next_edition_number"), 1)


def _is_sold_out(row):
    status = _plain_text(row.get("edition_status") or row.get("run_status")).lower()
    return bool(row.get("sold_out") or row.get("is_sold_out")) or status in {"sold_out", "sold out", "archived", "archive"}


def _edition_stage_from_number(next_number, total=100, sold_out=False):
    if sold_out:
        return "Archived"
    if not next_number:
        return "Generic / Unknown"
    current = max(min(_int(next_number, 1), _int(total, 100)), 1)
    if current <= 10:
        return "Low Number Rush"
    if current <= 30:
        return "Early Run"
    if current <= 49:
        return "Momentum Building"
    if current <= 60:
        return "Halfway Mark"
    if current <= 70:
        return "Demand Building"
    if current <= 80:
        return "Running Hot"
    if current <= 90:
        return "Late Stage"
    if current <= 95:
        return "Near The End"
    if current <= 98:
        return "Closing Fast"
    return "Final Call"


def _edition_stage_rules(stage):
    rules = {
        "Low Number Rush": "Low numbers go first. Claim yours early. Be early to the drop. Do not fake demand.",
        "Early Run": "The first wave is moving. Early run is open. Still early, not forever.",
        "Momentum Building": "Momentum is building. The run is moving. Do not overclaim sellout risk.",
        "Halfway Mark": "The window is narrowing. This drop has crossed the halfway mark. Not early anymore.",
        "Demand Building": "Demand is building. Do not leave it too late. The run is getting tighter.",
        "Running Hot": "Running hot. The best window is closing. Waiting gets harder from here.",
        "Late Stage": "Late stage. Waiting gets riskier now. The door is closing.",
        "Near The End": "Near the end. The final stretch is here. Almost archived.",
        "Closing Fast": "Closing fast. Last chance to get in. This is nearly over.",
        "Final Call": "Final call. This drop closes after this. Once it closes, it moves to the archive.",
        "Archived": "Archived. This release will not return. Use proof, not sales copy.",
        "Generic / Unknown": "Edition data is missing. Use safe generic limited-run language only. Do not fake scarcity.",
    }
    return rules.get(stage, rules["Generic / Unknown"])


def _infer_sport(row, manual_value=""):
    manual = _plain_text(manual_value)
    if manual:
        return manual
    text = f"{_product_title(row)} {_product_handle(row)}".lower()
    sports = (
        ("Basketball", ("kobe", "jordan", "lebron", "nba", "basketball")),
        ("Motorsport", ("f1", "formula", "senna", "schumacher", "motorsport", "racing")),
        ("Football / Soccer", ("arsenal", "football", "soccer", "messi", "ronaldo")),
        ("Cricket", ("cricket", "warne", "bradman")),
        ("Combat Sports", ("boxing", "ufc", "fight", "ali", "tyson")),
        ("Horse Racing", ("horse", "racing", "phar lap")),
        ("Baseball", ("baseball", "mlb", "yankees")),
        ("Hockey", ("hockey", "nhl")),
    )
    for sport, keywords in sports:
        if any(word in text for word in keywords):
            return sport
    return "Sport not specified"


def _product_label(row):
    title = _product_title(row)
    handle = _product_handle(row)
    remaining = _remaining(row)
    if handle:
        return f"{title} | {handle} | {remaining} left"
    return title


def _format_time(value):
    if not value:
        return "Never"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone().strftime("%d %b %Y %I:%M %p")
    except ValueError:
        return str(value)


def _meta_rows_for_product(meta_summary, product):
    handle = _product_handle(product).lower()
    title = _product_title(product).lower()
    rows = []
    for row in meta_summary.get("mapping") or []:
        row_blob = " ".join(
            _plain_text(row.get(key)).lower()
            for key in ("product_handle", "product_title", "suggested_product_handle", "suggested_product_title", "ad_name", "campaign_name")
        )
        if handle and handle in row_blob:
            rows.append(row)
        elif title and title != "manual product" and title in row_blob:
            rows.append(row)
    return sorted(rows, key=lambda item: (_num(item.get("purchase_value")), _num(item.get("spend"))), reverse=True)


def _meta_signal_summary(rows):
    if not rows:
        return "No Meta signal found for this product yet. Use product story + edition stage."
    top = rows[0]
    label = top.get("ad_name") or top.get("campaign_name") or "Mapped Meta ad"
    return (
        f"Top stored Meta signal: {label}. Spend {_money(top.get('spend'))}, "
        f"purchases {_int(top.get('purchases'))}, ROAS {_ratio(top.get('roas'))}, "
        f"CTR {_pct(top.get('ctr'))}. Suggested action: {_decision_label(top)}."
    )


def _decision_label(row):
    purchases = _num(row.get("purchases"))
    roas = _num(row.get("roas"))
    spend = _num(row.get("spend"))
    clicks = _num(row.get("clicks"))
    ctr = _num(row.get("ctr"))
    if purchases >= 2 and roas >= 2.5:
        return "Scale candidate"
    if spend >= 30 and clicks >= 25 and purchases <= 0:
        return "Landing page/product issue"
    if spend > 0 and purchases <= 0:
        return "Refresh creative"
    if ctr < 0.8 and spend > 20:
        return "Kill candidate"
    if spend < 20:
        return "Needs more spend"
    return "Watch"


def _short_headlines(primary_angle, stage):
    base = {
        "Nostalgia": ["The Moment Lives", "Real Fans Remember", "History, Framed", "The Era Remains"],
        "Identity": ["For Real Fans", "Not For Casuals", "Wall Pride", "Your Club Wall"],
        "Collector Value": ["Numbered Run", "One Of 100", "Built To Claim", "Collector Owned"],
        "Australian / Man Cave / Clubroom": ["Man Cave Ready", "Clubroom Ready", "Built Proper", "Wall With Story"],
        "Scarcity": ["No Reprints", "Strictly Limited", "Window Is Narrowing", "Do Not Wait"],
        "Rivalry / Debate": ["Debate Lives", "One Wall Debate", "Legacy Vs Legacy", "Still Argued"],
        "Hero Moment": ["The Moment Lives", "Peak Captured", "Sport Stood Still", "Never Forgotten"],
        "Gift Buyer": ["For The Fan", "Not Another Gift", "Their Wall Moment", "Fan Who Has Everything"],
        "Room Upgrade": ["Built For Walls", "Home Bar Ready", "Room With Story", "Wall That Matters"],
        "Final Editions": ["Final Stretch", "Almost Archived", "Final Call", "Nearly Gone"],
    }.get(primary_angle, ["The Moment Lives", "For Real Fans", "Numbered Run", "No Reprints"])
    stage_hooks = {
        "Low Number Rush": ["Claim Yours Early", "Low Numbers First"],
        "Early Run": ["First Wave Moving", "Still Early"],
        "Momentum Building": ["Momentum Building", "Run Is Moving"],
        "Halfway Mark": ["Not Early Now", "Window Narrowing"],
        "Demand Building": ["Demand Building", "Getting Tighter"],
        "Running Hot": ["Running Hot", "Window Closing"],
        "Late Stage": ["Late Stage", "Door Is Closing"],
        "Near The End": ["Near The End", "Final Stretch"],
        "Closing Fast": ["Closing Fast", "Nearly Over"],
        "Final Call": ["Final Call", "Last Chance"],
    }.get(stage, ["Limited Run", "Collector Piece"])
    output = []
    for item in base + stage_hooks + ["Built For The Wall", "No Reprints"]:
        if item not in output:
            output.append(item)
    return output[:8]


def _descriptions(stage):
    options = [
        "Numbered run",
        "Built for real fans",
        "Framed or unframed",
        "No reprints",
        "Claim yours early",
        "Collector release",
        "Made for the wall",
        "Once gone, archived",
    ]
    if stage in {"Late Stage", "Near The End", "Closing Fast", "Final Call"}:
        options = [
            "Late-stage run",
            "Final numbers remain",
            "No reprints",
            "Once gone, archived",
            "Built for real fans",
            "Collector release",
            "Framed or unframed",
            "Do not wait",
        ]
    if stage == "Generic / Unknown":
        options = [
            "Numbered collector run",
            "Built for real fans",
            "Framed or unframed",
            "No generic poster feel",
            "Made for the wall",
            "Collector release",
            "Premium sports art",
            "Use safe scarcity",
        ]
    return options[:8]


def _primary_texts(product_name, fan_base, country, stage, primary_angle):
    fan_line = fan_base or "real fans"
    return [
        f"{product_name} belongs on the wall of {fan_line}. A collector-led piece built around the moment, not generic poster copy.",
        f"For {fan_line} who still remember why this mattered. {stage} energy, {COUNTRY_RULES.get(country, COUNTRY_RULES['Universal']).split('.')[0].lower()}.",
        f"Make the wall say something. {product_name} brings the story, the run, and the {primary_angle.lower()} angle into one clean drop.",
    ]


def _carousel_cards(product_name, stage, primary_angle):
    headlines = _short_headlines(primary_angle, stage)
    return [
        {"card": 1, "label": headlines[0], "subline": "Hero mockup", "reason": "Hero moment", "image": "Clean product hero or main wall mockup"},
        {"card": 2, "label": headlines[1], "subline": "Identity angle", "reason": "Nostalgia or identity", "image": "Close crop of artwork detail"},
        {"card": 3, "label": "Built For The Wall", "subline": "Room proof", "reason": "Room/man cave/clubroom", "image": "Framed room mockup"},
        {"card": 4, "label": "Numbered Run", "subline": "Collector ownership", "reason": "Collector value", "image": "Edition/detail crop"},
        {"card": 5, "label": headlines[-1], "subline": "Clear CTA", "reason": "Scarcity/CTA", "image": f"{product_name} in final clean product layout"},
    ]


def _build_prompt(inputs):
    angle_rules = ANGLE_RULES.get(inputs["primary_angle"], "")
    secondary = ", ".join(inputs["secondary_angles"]) if inputs["secondary_angles"] else "None"
    exact_rule = "Exact edition number is enabled. Only use it if the ad will be updated when numbers move." if inputs["include_exact"] else "Do not mention exact edition number unless I explicitly ask."
    return f"""START PROMPT

You are my Sports Cave Meta Ads strategist and copywriter.

PRODUCT:
- Product name: {inputs['product_name']}
- Product handle: {inputs['product_handle']}
- Sport: {inputs['sport']}
- Fan base: {inputs['fan_base']}
- Country target: {inputs['country']}
- Ad format: {inputs['ad_format']}
- Funnel stage: {inputs['funnel_stage']}
- Edition stage: {inputs['edition_stage']}
- Edition truth: {inputs['edition_truth']}
- Product story/context: {inputs['story_context']}
- Existing Meta signal: {inputs['meta_signal']}
- Primary angle: {inputs['primary_angle']}
- Secondary angles: {secondary}

SPORTS CAVE BRAND:
Sports Cave sells premium framed and unframed sports wall art for real fans, collectors, man caves, clubrooms, home bars, garages, offices, and gift buyers.

The copy must feel:
- nostalgic
- collector-driven
- emotional
- premium
- urgent
- short and human
- masculine where appropriate
- fan-specific
- country-specific

The copy must not feel:
- corporate
- generic
- cheap
- over-explained
- AI-sounding
- like normal poster/wall decor copy

ANGLE RULES:
Use the chosen angle:
{angle_rules}

COUNTRY RULES:
Use the country target tone:
{COUNTRY_RULES.get(inputs['country'], COUNTRY_RULES['Universal'])}

EDITION STAGE RULES:
Use edition stage language:
{_edition_stage_rules(inputs['edition_stage'])}

{exact_rule}
Do not make false scarcity claims.
The product page will show exact edition number. The ad should use broader stage language.

AD FORMAT:
{AD_FORMAT_RULES.get(inputs['ad_format'], '')}

OUTPUT EXACTLY:

1. Campaign angle
- One sentence.

2. Target audience
- Primary audience.
- Secondary audience.
- Why they care.

3. Primary text
Write 3 variants.
Each must be short, emotional, and human.
No generic poster language.

4. Headlines
Write 8 options.
Max 4 words each.
Must fit mobile.

5. Descriptions
Write 8 options.
Max 6 words each.
Must fit mobile.

6. Manual carousel card copy
Write 5 cards.
Each card:
- card label
- optional subline max 6 words
- buying reason
- suggested mockup/image

Cards must create different buying reasons:
Card 1: hero moment
Card 2: nostalgia/identity
Card 3: wall/man cave/clubroom
Card 4: numbered run/collector ownership
Card 5: scarcity/CTA

7. Retargeting version
Write 2 variants.
Use warmer urgency.
No cheap discount language.

8. Final scarcity version
Write 2 variants.
Only use if edition stage supports it.
Keep it premium.

9. Instant Experience version
If the ad format includes Instant Experience, write:
- feed hero copy
- banner overlay options
- opening hero section
- story/memory section
- wall/room proof section
- collector detail section
- catalogue/product set section
- final CTA section
- button text

10. Mockup/image brief
Write a clean brief for image generation or mockup selection.
The artwork must stay unchanged.
Use sport/country-appropriate room direction.
No clutter.
No fake logos.
No unrelated athletes.

11. Quality checklist
Answer:
- Does every carousel headline fit on mobile?
- Does every description fit on mobile?
- Does each card create a different buying reason?
- Does copy feel like collector art, not a poster?
- Is nostalgia or identity clear early?
- Is scarcity clear by final card?
- Would the target country understand the tone?
- Is anything too generic, too long, too polished, or AI-sounding?
- Is there a clear CTA?
- Does it match the true fan base?

HARD AVOID:
Do not use:
{chr(10).join(HARD_AVOID)}

END PROMPT"""


def _build_pack(inputs):
    prompt = _build_prompt(inputs)
    headlines = _short_headlines(inputs["primary_angle"], inputs["edition_stage"])
    descriptions = _descriptions(inputs["edition_stage"])
    primary_texts = _primary_texts(
        inputs["product_name"],
        inputs["fan_base"],
        inputs["country"],
        inputs["edition_stage"],
        inputs["primary_angle"],
    )
    cards = _carousel_cards(inputs["product_name"], inputs["edition_stage"], inputs["primary_angle"])
    strategy = "\n".join(
        [
            f"Product: {inputs['product_name']} ({inputs['product_handle'] or 'manual product'})",
            f"Market: {inputs['country']} | Format: {inputs['ad_format']} | Funnel: {inputs['funnel_stage']}",
            f"Edition: {inputs['edition_stage']} - {inputs['edition_truth']}",
            f"Primary angle: {inputs['primary_angle']}",
            f"Meta signal: {inputs['meta_signal']}",
            "Next step: paste the full prompt into ChatGPT with the product artwork/mockups, then run the checklist before publishing.",
        ]
    )
    carousel_lines = ["Manual Carousel Upload Pack", "", "Campaign angle:", f"- {inputs['primary_angle']} for {inputs['fan_base'] or 'real fans'}.", "", "Primary text variants:"]
    carousel_lines.extend(f"{index}. {text}" for index, text in enumerate(primary_texts, 1))
    carousel_lines.extend(["", "Carousel cards:"])
    for card in cards:
        carousel_lines.append(f"{card['card']}. {card['label']} - {card['subline']} | {card['reason']} | Image: {card['image']}")
    instant = "\n".join(
        [
            "Instant Experience + Catalogue Pack",
            "",
            "Feed hero / banner:",
            f"- Primary text angle: {inputs['primary_angle']} with {inputs['country']} tone.",
            f"- Banner overlay options: {', '.join(headlines[:3])}",
            f"- CTA recommendation: View the drop",
            "",
            "Opening Hero: premium product wall mockup, short overlay, one clean CTA.",
            "Story / Memory: explain why the fan remembers this product or moment.",
            "Wall / Room Proof: show the piece in a country-appropriate room.",
            "Collector Detail: mention numbered run and finish without overclaiming scarcity.",
            "Product Set / Catalogue: attach catalogue as the buying section after the story.",
            f"Final CTA: {_edition_stage_rules(inputs['edition_stage'])}",
        ]
    )
    retargeting = "\n".join(
        [
            "Retargeting Pack",
            "",
            f"1. You viewed {inputs['product_name']}. If it belongs on your wall, do not leave the run too late.",
            f"2. {inputs['product_name']} is for {inputs['fan_base'] or 'real fans'} who know the story. Framed or unframed, numbered, and built for the wall.",
        ]
    )
    scarcity_allowed = inputs["edition_stage"] in {"Running Hot", "Late Stage", "Near The End", "Closing Fast", "Final Call"}
    scarcity_note = "Use now." if scarcity_allowed else "Keep as a future-ready section. Do not claim final editions until the edition stage supports it."
    final_scarcity = "\n".join(
        [
            "Final Scarcity Pack",
            scarcity_note,
            "",
            f"1. {inputs['edition_stage']}: the window is narrowing. Once this closes, it moves to the archive.",
            f"2. The final stretch is where waiting gets expensive. Claim {inputs['product_name']} before the run closes.",
        ]
    )
    mockup = "\n".join(
        [
            "Mockup / Image Brief",
            f"- Keep the supplied artwork unchanged for {inputs['product_name']}.",
            f"- Use {inputs['sport']} environment cues only if subtle.",
            f"- Country direction: {COUNTRY_RULES.get(inputs['country'], COUNTRY_RULES['Universal']).split('.')[0]}.",
            "- Use realistic glass, shadow, frame depth, and a premium room.",
            "- Avoid clutter, fake logos, unrelated athletes, and warped frames.",
            f"- Notes: {inputs['mockup_notes'] or 'Use clean product and room mockups.'}",
        ]
    )
    checklist = "\n".join(f"- {item}" for item in QUALITY_CHECKS)
    return {
        "strategy": strategy,
        "full_prompt": prompt,
        "carousel": "\n".join(carousel_lines),
        "instant_experience": instant,
        "retargeting": retargeting,
        "final_scarcity": final_scarcity,
        "headlines": "\n".join(f"- {item}" for item in headlines),
        "descriptions": "\n".join(f"- {item}" for item in descriptions),
        "carousel_labels": "\n".join(f"- Card {card['card']}: {card['label']} ({card['reason']})" for card in cards),
        "mockup_brief": mockup,
        "quality_checklist": checklist,
        "generated_at": _now_iso(),
        "input_payload": inputs,
    }


def _markdown_export(pack):
    sections = [
        ("Strategy Summary", pack.get("strategy")),
        ("Sports Cave Copy Prompt", pack.get("full_prompt")),
        ("Manual Carousel Upload Pack", pack.get("carousel")),
        ("Instant Experience + Catalogue Pack", pack.get("instant_experience")),
        ("Retargeting Pack", pack.get("retargeting")),
        ("Final Scarcity Pack", pack.get("final_scarcity")),
        ("Headline Bank", pack.get("headlines")),
        ("Description Bank", pack.get("descriptions")),
        ("Carousel Card Labels", pack.get("carousel_labels")),
        ("Mockup / Image Brief", pack.get("mockup_brief")),
        ("Quality Checklist", pack.get("quality_checklist")),
    ]
    lines = ["# Sports Cave Marketing Factory Pack", ""]
    for title, body in sections:
        lines.extend([f"## {title}", "", str(body or ""), ""])
    return "\n".join(lines)


def _pack_payload(pack, status="Draft"):
    inputs = pack.get("input_payload") or {}
    return {
        "product_handle": inputs.get("product_handle"),
        "product_title": inputs.get("product_name"),
        "shopify_product_id": inputs.get("shopify_product_id"),
        "country": inputs.get("country"),
        "ad_format": inputs.get("ad_format"),
        "funnel_stage": inputs.get("funnel_stage"),
        "edition_stage": inputs.get("edition_stage"),
        "next_edition_number": inputs.get("next_edition_number"),
        "edition_total": inputs.get("edition_total"),
        "edition_remaining": inputs.get("edition_remaining"),
        "primary_angle": inputs.get("primary_angle"),
        "secondary_angles": inputs.get("secondary_angles") or [],
        "input_payload": inputs,
        "generated_prompt": pack.get("full_prompt"),
        "generated_preview": {key: value for key, value in pack.items() if key not in {"full_prompt", "input_payload"}},
        "status": status,
    }


def _render_header():
    selected_stage = st.session_state.get("mf_selected_stage") or "Not selected"
    chips = [
        ("Start", "Choose product"),
        ("Then", "Pick market"),
        ("Next", "Generate pack"),
        ("Current stage", selected_stage),
        ("Safety", "No live ad changes"),
    ]
    chip_html = "".join(f"<span class='mf-chip'><strong>{html.escape(label)}:</strong> {html.escape(value)}</span>" for label, value in chips)
    st.markdown(
        f"""
        <div class="mf-header">
          <h1>Marketing Factory</h1>
          <p>Build Meta ad prompts from product, edition, and Meta performance signals.</p>
        </div>
        <div class="mf-chip-row">{chip_html}</div>
        """,
        unsafe_allow_html=True,
    )


def _product_selector(products):
    options = ["Manual / no product"] + [_product_label(row) for row in products]
    selected_label = st.selectbox("Product", options, key="mf_product_select")
    if selected_label == "Manual / no product":
        return {}
    index = options.index(selected_label) - 1
    return products[index] if 0 <= index < len(products) else {}


def _render_meta_signal_panel(product, meta_summary):
    with _card("Meta Signal", "Optional past ad results. Buttons only fill this prompt builder."):
        if st.button("Load Meta Signals", use_container_width=True, key="mf-load-builder-meta"):
            st.session_state["mf_ad_builder_meta_loaded"] = True
            st.session_state["mf_ad_builder_meta_summary"] = _load_meta_summary("last_30_days")
        if not st.session_state.get("mf_ad_builder_meta_loaded"):
            st.info("Load Meta Signals only if you want past ad results to guide this pack.")
            return "No Meta signal loaded. Use product story + edition stage."
        meta_summary = st.session_state.get("mf_ad_builder_meta_summary") or meta_summary or {"mapping": []}
        rows = _meta_rows_for_product(meta_summary, product) if product else []
        if not rows:
            st.info("No Meta signal found for this product yet. Use product story + edition stage.")
            return "No Meta signal found for this product yet. Use product story + edition stage."
        top_rows = rows[:5]
        table = [
            {
                "Ad": row.get("ad_name") or row.get("campaign_name") or "Stored ad",
                "Decision": _decision_label(row),
                "Spend": _money(row.get("spend")),
                "Purchases": _int(row.get("purchases")),
                "ROAS": _ratio(row.get("roas")),
                "CTR": _pct(row.get("ctr")),
            }
            for row in top_rows
        ]
        st.dataframe(table, hide_index=True, use_container_width=True, height=180)
        button_cols = st.columns(2)
        if button_cols[0].button("Use winning hook", use_container_width=True, key="mf-use-winning-hook"):
            st.session_state["mf_story_context"] = _meta_signal_summary(rows)
            st.session_state["mf_primary_angle"] = "Nostalgia"
            st.success("Winning hook added to Story Notes.")
        if button_cols[1].button("Use refresh angle", use_container_width=True, key="mf-use-refresh-angle"):
            st.session_state["mf_story_context"] = "Product needs fresh creative. Use a new hook, clearer fan identity, and a sharper carousel structure."
            st.session_state["mf_primary_angle"] = "Hero Moment"
            st.success("Creative refresh angle loaded.")
        button_cols = st.columns(2)
        if button_cols[0].button("Use final-edition angle", use_container_width=True, key="mf-use-final-angle"):
            st.session_state["mf_primary_angle"] = "Final Editions"
            st.session_state["mf_funnel_stage"] = "Final Editions"
            st.success("Final-edition angle selected.")
        if button_cols[1].button("Use retargeting angle", use_container_width=True, key="mf-use-retargeting-angle"):
            st.session_state["mf_funnel_stage"] = "Retargeting Product Viewers"
            st.session_state["mf_story_context"] = "Use warm retargeting. Remind viewers of the product without sounding creepy."
            st.success("Retargeting angle selected.")
        return _meta_signal_summary(rows)


def _apply_pending_builder_prefill(products):
    pending = st.session_state.pop("mf_pending_prefill", None)
    if not pending:
        return
    handle = _plain_text(pending.get("product_handle"))
    title = _plain_text(pending.get("product_title"))
    matched = None
    for row in products:
        if handle and _product_handle(row).lower() == handle.lower():
            matched = row
            break
    if matched:
        st.session_state["mf_product_select"] = _product_label(matched)
        st.session_state["mf_loaded_product_key"] = _product_handle(matched) or _product_id(matched) or "manual"
        st.session_state["mf_product_title"] = _product_title(matched)
        st.session_state["mf_product_handle"] = _product_handle(matched)
        st.session_state["mf_product_url"] = _plain_text(matched.get("online_store_url") or matched.get("product_url"))
        st.session_state["mf_sport"] = _infer_sport(matched)
    elif title or handle:
        st.session_state["mf_product_select"] = "Manual / no product"
        st.session_state["mf_loaded_product_key"] = "manual"
        st.session_state["mf_product_title"] = title or handle
        st.session_state["mf_product_handle"] = handle
    if pending.get("country") in COUNTRY_OPTIONS:
        st.session_state["mf_country"] = pending["country"]
    if pending.get("funnel_stage") in FUNNEL_OPTIONS:
        st.session_state["mf_funnel_stage"] = pending["funnel_stage"]
    if pending.get("primary_angle") in ANGLE_OPTIONS:
        st.session_state["mf_primary_angle"] = pending["primary_angle"]
    if pending.get("story_context"):
        st.session_state["mf_story_context"] = pending["story_context"]


def _render_product_facts(product):
    with _card("Product", "Choose a product, or build a manual pack without loading data."):
        search = st.text_input(
            "Search products",
            value=st.session_state.get("mf_product_search_value", ""),
            placeholder="Search title or handle",
            key="mf_product_search_value",
        )
        load_cols = st.columns([1, 1])
        if load_cols[0].button("Load Products", use_container_width=True, key="mf-load-products"):
            st.session_state["mf_products_loaded"] = True
            st.session_state["mf_product_search_active"] = search
        if load_cols[1].button("Refresh Products", use_container_width=True, key="mf-refresh-products"):
            _load_product_options.clear()
            st.session_state["mf_products_loaded"] = True
            st.session_state["mf_product_search_active"] = search
        products = []
        if st.session_state.get("mf_products_loaded"):
            products = _load_product_options(st.session_state.get("mf_product_search_active", search), limit=150)
            if not products:
                st.warning("Product data unavailable. You can still create a manual prompt.")
        else:
            st.info("Click Load Products when you are ready to choose a product. Manual prompt creation is available now.")
        selected = _product_selector(products)
        if selected:
            product.clear()
            product.update(selected)
        selected_key = _product_handle(product) or _product_id(product) or "manual"
        if st.session_state.get("mf_loaded_product_key") != selected_key:
            st.session_state["mf_loaded_product_key"] = selected_key
            st.session_state["mf_product_title"] = _product_title(product) if product else ""
            st.session_state["mf_product_handle"] = _product_handle(product) if product else ""
            st.session_state["mf_product_url"] = _plain_text(product.get("online_store_url") or product.get("product_url")) if product else ""
            st.session_state["mf_sport"] = _infer_sport(product) if product else ""
            if product:
                st.session_state["mf_edition_stage"] = _edition_stage_from_number(
                    _next_number(product),
                    _edition_total(product),
                    _is_sold_out(product),
                )
        manual_title_default = _product_title(product) if product else ""
        product_name = st.text_input("Product title", value=manual_title_default, key="mf_product_title")
        product_handle = st.text_input("Product handle", value=_product_handle(product), key="mf_product_handle")
        product_url = st.text_input(
            "Product URL",
            value=_plain_text(product.get("online_store_url") or product.get("product_url")) if product else "",
            key="mf_product_url",
        )
        admin_url = _plain_text(product.get("admin_url")) if product else ""
        cols = st.columns(4)
        cols[0].metric("Next", _next_number(product) if product else "-")
        cols[1].metric("Total", _edition_total(product) if product else "-")
        cols[2].metric("Remaining", _remaining(product) if product else "-")
        cols[3].metric("Status", _plain_text(product.get("edition_status") or product.get("status"), "Unknown") if product else "Manual")
        if product and admin_url:
            st.link_button("Open Shopify", admin_url, use_container_width=True)
        if not product:
            st.warning("No product selected. You can still build a generic prompt, but edition scarcity must stay generic.")
        elif not _product_handle(product):
            st.warning("This product has no edition handle. Use safe generic copy and do not fake scarcity.")
    return product_name, product_handle, product_url


def _render_ad_builder():
    products = []
    if st.session_state.get("mf_products_loaded"):
        products = _load_product_options(st.session_state.get("mf_product_search_active", ""), limit=150)
    _apply_pending_builder_prefill(products)
    meta_summary = st.session_state.get("mf_ad_builder_meta_summary") or {"insights": [], "mapping": [], "opportunities": [], "actions": []}
    product = {}
    left, right = st.columns([0.95, 1.2], gap="large")

    with left:
        product_name, product_handle, product_url = _render_product_facts(product)
        meta_signal = _render_meta_signal_panel(product, meta_summary)
        next_number = _next_number(product) if product else 0
        total = _edition_total(product) if product else 100
        remaining = _remaining(product) if product else None
        derived_stage = _edition_stage_from_number(next_number, total, _is_sold_out(product) if product else False)
        st.session_state["mf_selected_stage"] = derived_stage

        with _card("Market", "Choose the country tone before writing copy."):
            country = st.selectbox("Country target", COUNTRY_OPTIONS, index=0, key="mf_country")
            st.caption(COUNTRY_RULES[country])

        with _card("Ad Format", "Choose the output pack you are building today."):
            ad_format = st.selectbox("Ad format", AD_FORMAT_OPTIONS, index=0, key="mf_ad_format")
            st.caption(AD_FORMAT_RULES[ad_format])

        with _card("Funnel Stage", "This decides how hard the copy can push."):
            funnel_stage = st.selectbox("Funnel stage", FUNNEL_OPTIONS, index=0, key="mf_funnel_stage")
            st.caption(FUNNEL_RULES[funnel_stage])

        with _card("Edition Stage", "Autofilled when product data is loaded. Manual override affects this prompt only."):
            manual_stage = st.selectbox(
                "Edition stage for prompt",
                EDITION_STAGE_OPTIONS,
                index=EDITION_STAGE_OPTIONS.index(derived_stage) if derived_stage in EDITION_STAGE_OPTIONS else len(EDITION_STAGE_OPTIONS) - 1,
                key="mf_edition_stage",
            )
            if manual_stage != derived_stage:
                st.warning("Manual override changes the ad prompt only. It does not update product records or edition numbers.")
            include_exact = st.checkbox("Include exact edition number in prompt", value=False, key="mf_include_exact")
            if include_exact:
                st.warning("Only use exact edition numbers if the ad will be updated when numbers move.")

        with _card("Copy Angle", "Pick one primary angle and optional supporting angles."):
            primary_angle = st.selectbox("Primary angle", ANGLE_OPTIONS, index=0, key="mf_primary_angle")
            secondary_angles = st.multiselect(
                "Secondary angles",
                ANGLE_OPTIONS,
                default=["Collector Value", "Scarcity"] if primary_angle not in {"Collector Value", "Scarcity"} else ["Nostalgia"],
                key="mf_secondary_angles",
            )

        with _card("Story Notes", "Keep this practical. A VA should know exactly what to paste next."):
            sport = st.text_input("Sport", value=_infer_sport(product), key="mf_sport")
            fan_base = st.text_input("Fan base", value="", placeholder="Example: Lakers fans, Arsenal supporters, motorsport collectors", key="mf_fan_base")
            story_context = st.text_area("Story/context behind the artwork", height=90, key="mf_story_context")
            rivalry_notes = st.text_area("Rivalry / legacy / moment notes", height=70, key="mf_rivalry_notes")
            product_angle_notes = st.text_area("Product angle notes", height=70, key="mf_product_angle_notes")
            mockup_notes = st.text_area("Mockup / image notes", height=70, key="mf_mockup_notes")
            emotional_value = st.text_area("What makes this emotionally valuable?", height=70, key="mf_emotional_value")
            avoid_words = st.text_input("Words to avoid for this product", key="mf_avoid_words")

        with _card("Output Controls", "Leave defaults on for a full VA-ready prompt pack."):
            include_controls = {
                "primary_text": st.checkbox("Include primary text", value=True, key="mf_include_primary"),
                "short_primary": st.checkbox("Include short primary text", value=True, key="mf_include_short_primary"),
                "headlines": st.checkbox("Include headlines", value=True, key="mf_include_headlines"),
                "descriptions": st.checkbox("Include descriptions", value=True, key="mf_include_descriptions"),
                "carousel": st.checkbox("Include carousel card labels", value=True, key="mf_include_carousel"),
                "retargeting": st.checkbox("Include retargeting copy", value=True, key="mf_include_retargeting"),
                "final_scarcity": st.checkbox("Include final scarcity copy", value=True, key="mf_include_final"),
                "instant": st.checkbox("Include Instant Experience storyboard", value=True, key="mf_include_instant"),
                "mockup": st.checkbox("Include mockup/image brief", value=True, key="mf_include_mockup"),
                "quality": st.checkbox("Include quality checklist", value=True, key="mf_include_quality"),
                "full_prompt": st.checkbox("Include full copy/paste ChatGPT prompt", value=True, key="mf_include_full_prompt"),
                "csv": st.checkbox("Include CSV export format", value=False, key="mf_include_csv"),
            }
            save_after = st.checkbox("Save pack after generation", value=False, key="mf_save_after_generate")

        edition_truth = "Edition data missing. Use safe generic copy." if not product else (
            f"{manual_stage}. Next edition {next_number} of {total}; {remaining} remaining."
            if include_exact
            else f"{manual_stage}. Use broad stage language; product page handles exact numbers."
        )
        inputs = {
            "product_name": product_name or "Manual product",
            "product_handle": product_handle,
            "shopify_product_id": _product_id(product),
            "product_url": product_url,
            "sport": sport,
            "fan_base": fan_base,
            "country": country,
            "ad_format": ad_format,
            "funnel_stage": funnel_stage,
            "edition_stage": manual_stage,
            "edition_truth": edition_truth,
            "next_edition_number": next_number,
            "edition_total": total,
            "edition_remaining": remaining,
            "story_context": "\n".join(part for part in [story_context, rivalry_notes, product_angle_notes, emotional_value, avoid_words] if part),
            "mockup_notes": mockup_notes,
            "meta_signal": meta_signal,
            "primary_angle": primary_angle,
            "secondary_angles": secondary_angles,
            "include_exact": include_exact,
            "include_controls": include_controls,
        }
        if st.button("Generate Prompt Pack", type="primary", use_container_width=True, key="mf_generate_pack"):
            pack = _build_pack(inputs)
            st.session_state["mf_generated_pack"] = pack
            if save_after and supabase_backend.is_configured():
                try:
                    saved = supabase_backend.save_ads_copy_pack(_pack_payload(pack), created_by="marketing_factory")
                    st.session_state["mf_last_save"] = saved
                    _load_saved_packs.clear()
                except Exception:
                    st.session_state["mf_last_save"] = {"saved": False}
            st.success("Prompt pack generated.")

    with right:
        pack = st.session_state.get("mf_generated_pack")
        with _card("Generated Output", "Copy one section at a time, or download the whole pack."):
            if not pack:
                st.info("Select a product, choose market/format/stage, then click Generate Prompt Pack.")
                return
            _render_outputs(pack)


def _render_outputs(pack):
    full_prompt = pack.get("full_prompt", "")
    top_cols = st.columns([1, 1, 1])
    with top_cols[0]:
        _copy_button(full_prompt, "full-prompt-top", "Copy Full Prompt")
    with top_cols[1]:
        st.download_button(
            "Download Markdown",
            data=_markdown_export(pack).encode("utf-8"),
            file_name="sports-cave-marketing-pack.md",
            mime="text/markdown",
            use_container_width=True,
            key="mf-download-md",
        )
    with top_cols[2]:
        st.download_button(
            "Download JSON",
            data=json.dumps(pack, indent=2, default=_json_default).encode("utf-8"),
            file_name="sports-cave-marketing-pack.json",
            mime="application/json",
            use_container_width=True,
            key="mf-download-json",
        )
    save_cols = st.columns([1, 1, 1])
    if save_cols[0].button("Save", use_container_width=True, key="mf-save-pack"):
        try:
            saved = supabase_backend.save_ads_copy_pack(_pack_payload(pack), created_by="marketing_factory")
            st.success(f"Saved pack {saved.get('id')}.")
            _load_saved_packs.clear()
        except Exception:
            st.error("Pack could not be saved. You can still copy or download it.")
    if save_cols[1].button("Mark Ready", use_container_width=True, key="mf-save-ready"):
        try:
            saved = supabase_backend.save_ads_copy_pack(_pack_payload(pack, status="Ready"), created_by="marketing_factory")
            st.success(f"Saved as Ready: {saved.get('id')}.")
            _load_saved_packs.clear()
        except Exception:
            st.error("Pack could not be saved. You can still copy or download it.")
    if save_cols[2].button("Mark Needs Review", use_container_width=True, key="mf-save-review"):
        try:
            saved = supabase_backend.save_ads_copy_pack(_pack_payload(pack, status="Needs Review"), created_by="marketing_factory")
            st.success(f"Saved as Needs Review: {saved.get('id')}.")
            _load_saved_packs.clear()
        except Exception:
            st.error("Pack could not be saved. You can still copy or download it.")

    section_map = [
        ("Strategy Summary", "strategy", "Copy Strategy"),
        ("Full Prompt", "full_prompt", "Copy Full Prompt"),
        ("Carousel Pack", "carousel", "Copy Carousel Pack"),
        ("Instant Experience Pack", "instant_experience", "Copy Instant Pack"),
        ("Retargeting Pack", "retargeting", "Copy Retargeting"),
        ("Final Scarcity Pack", "final_scarcity", "Copy Scarcity"),
        ("Headlines", "headlines", "Copy Headlines"),
        ("Descriptions", "descriptions", "Copy Descriptions"),
        ("Carousel Card Labels", "carousel_labels", "Copy Card Labels"),
        ("Mockup / Image Brief", "mockup_brief", "Copy Mockup Brief"),
        ("Quality Checklist", "quality_checklist", "Copy Checklist"),
    ]
    for title, key, copy_label in section_map:
        with st.expander(title, expanded=title in {"Strategy Summary", "Full Prompt"}):
            body = pack.get(key, "")
            _copy_button(body, f"section-{key}", copy_label)
            st.text_area(title, value=body, height=260 if key == "full_prompt" else 170, key=f"mf-output-{key}", label_visibility="collapsed")


def _render_meta_intelligence_tab():
    st.subheader("Meta Signals")
    st.caption("Use past ad results to choose better hooks. This page only helps build copy packs.")
    date_range = st.selectbox("Date range", ["last_7_days", "last_14_days", "last_30_days", "last_90_days", "all"], index=2, key="mf-meta-date")
    market = st.selectbox("Market", ["All", *COUNTRY_OPTIONS], key="mf-meta-market")
    product_query = st.text_input("Product filter", key="mf-meta-product-filter")
    signal_cols = st.columns([1, 1, 2])
    if signal_cols[0].button("Load Meta Signals", use_container_width=True, key="mf-load-meta-tab"):
        st.session_state["mf_meta_tab_loaded_range"] = date_range
        st.session_state["mf_meta_tab_summary"] = _load_meta_summary(date_range)
    if signal_cols[1].button("Refresh Signals", use_container_width=True, key="mf-refresh-meta-tab"):
        _load_meta_summary.clear()
        st.session_state["mf_meta_tab_loaded_range"] = date_range
        st.session_state["mf_meta_tab_summary"] = _load_meta_summary(date_range)
    if st.session_state.get("mf_meta_tab_loaded_range") != date_range:
        st.info("Click Load Meta Signals to see stored ad results for this range.")
        return
    data = st.session_state.get("mf_meta_tab_summary") or {"insights": [], "mapping": [], "opportunities": [], "actions": []}
    insights = data.get("insights") or []
    mapping = data.get("mapping") or []
    opportunities = data.get("opportunities") or []
    actions = data.get("actions") or []
    st.caption(f"Rows: {len(insights)} performance rows, {len(mapping)} mapped ads, {len(opportunities)} product opportunities.")

    summary_rows = [
        {
            "Ad": row.get("ad_name") or row.get("campaign_name") or "Stored ad",
            "Product": row.get("product_title") or row.get("product_handle") or row.get("suggested_product_title") or "",
            "Decision": _decision_label(row),
            "Spend": _money(row.get("spend")),
            "Purchases": _int(row.get("purchases")),
            "ROAS": _ratio(row.get("roas")),
            "CTR": _pct(row.get("ctr")),
        }
        for row in mapping
        if (market == "All" or market.lower() in _plain_text(row.get("country_focus")).lower())
        and (not product_query or product_query.lower() in " ".join(_plain_text(row.get(k)).lower() for k in ("product_title", "product_handle", "suggested_product_title", "ad_name")))
    ]
    with _card("Daily War Room", "Use these labels to decide what to write next."):
        st.dataframe(summary_rows[:100], hide_index=True, use_container_width=True, height=260)
    with _card("Creative Winner Board", "Top stored ads by purchases and ROAS."):
        winner_rows = sorted(mapping, key=lambda row: (_num(row.get("purchases")), _num(row.get("roas"))), reverse=True)[:12]
        st.dataframe(
            [
                {
                    "Ad": row.get("ad_name"),
                    "Product": row.get("product_title") or row.get("product_handle"),
                    "Hook": row.get("hook_style") or row.get("ad_angle") or "",
                    "ROAS": _ratio(row.get("roas")),
                    "Purchases": _int(row.get("purchases")),
                    "Action": _decision_label(row),
                }
                for row in winner_rows
            ],
            hide_index=True,
            use_container_width=True,
        )
        for row in winner_rows[:5]:
            button_label = f"Send To Ad Builder: {row.get('ad_name') or row.get('campaign_name') or 'Stored ad'}"
            if st.button(button_label, use_container_width=True, key=f"mf-send-builder-{_safe_key(row.get('ad_id') or button_label)}"):
                country = row.get("country_focus") if row.get("country_focus") in COUNTRY_OPTIONS else "Universal"
                funnel = row.get("funnel_stage") if row.get("funnel_stage") in FUNNEL_OPTIONS else "Warm Prospecting"
                angle = row.get("ad_angle") if row.get("ad_angle") in ANGLE_OPTIONS else "Nostalgia"
                st.session_state["mf_pending_prefill"] = {
                    "product_handle": row.get("product_handle") or row.get("suggested_product_handle") or "",
                    "product_title": row.get("product_title") or row.get("suggested_product_title") or "",
                    "country": country,
                    "funnel_stage": funnel,
                    "primary_angle": angle,
                    "story_context": _meta_signal_summary([row]),
                }
                st.session_state["mf_requested_tab"] = "Ad Builder"
                st.rerun()
    with _card("Product Mapping", "Shows which ads are tied to products."):
        st.dataframe(
            [
                {
                    "Ad": row.get("ad_name"),
                    "Product": row.get("product_title") or row.get("suggested_product_title") or row.get("product_handle"),
                    "Status": row.get("mapping_status"),
                    "Spend": _money(row.get("spend")),
                    "Recommendation": _decision_label(row),
                }
                for row in mapping[:200]
            ],
            hide_index=True,
            use_container_width=True,
            height=280,
        )
    with _card("Recent Signal Updates", "Recent stored updates for ad signal data."):
        st.dataframe(
            [
                {
                    "Created": _format_time(row.get("created_at")),
                    "Type": row.get("action_type"),
                    "Status": row.get("status"),
                    "Summary": row.get("summary"),
                }
                for row in actions[:40]
            ],
            hide_index=True,
            use_container_width=True,
        )


def _render_winning_angles_tab():
    st.subheader("Winning Angles")
    st.caption("Reusable Sports Cave strategy library.")
    cols = st.columns(2)
    groups = [
        ("Sports Cave Core Angles", ANGLE_RULES),
        ("Country Angles", COUNTRY_RULES),
        ("Funnel Stage Angles", FUNNEL_RULES),
        ("Edition Stage Angles", {stage: _edition_stage_rules(stage) for stage in EDITION_STAGE_OPTIONS}),
    ]
    for index, (title, data) in enumerate(groups):
        with cols[index % 2]:
            with _card(title, "Copy from here when planning a prompt."):
                for name, body in data.items():
                    with st.expander(name):
                        st.write(body)
    with _card("Avoid List", "Hard bans for Sports Cave Meta copy."):
        st.write(", ".join(HARD_AVOID))
        _copy_button("\n".join(HARD_AVOID), "winning-avoid-list", "Copy Avoid List")


def _render_prompt_library_tab():
    st.subheader("Prompt Library")
    st.caption("Locked templates with editable variables. No OpenAI calls.")
    templates = {
        "Full Meta Ad Copy Pack": "Use the Ad Builder full prompt for product-specific packs.",
        "Manual Carousel Upload": AD_FORMAT_RULES["Manual Carousel Upload"],
        "Instant Experience + Catalogue": AD_FORMAT_RULES["Instant Experience + Catalogue"],
        "Retargeting": AD_FORMAT_RULES["Retargeting"],
        "Final Editions": AD_FORMAT_RULES["Final Scarcity"],
        "Gift Buyer": FUNNEL_RULES["Gift Buyers"],
        "Mockup/Image Brief": "Create a clean mockup/image brief. Artwork unchanged. No fake logos. Country-appropriate room.",
        "Meta Performance Analysis Prompt": "Analyze stored Meta winners and losers. Recommend scale, refresh, kill, and next creative.",
        "Creative Refresh Prompt": "Create new hooks for weak ads without copying winners word-for-word.",
        "Product Opportunity Prompt": "Use product, edition, and stored Meta opportunity signals to decide what to test next.",
    }
    selected = st.selectbox("Template", list(templates), key="mf-template")
    variables = st.text_area(
        "Editable variables",
        value="Product:\nCountry:\nEdition stage:\nFan base:\nStory notes:\nMeta signal:",
        height=160,
        key="mf-template-vars",
    )
    preview = f"{selected}\n\nPurpose:\n{templates[selected]}\n\nVariables:\n{variables}\n\nRules:\n- No OpenAI call from Sports Cave OS.\n- Paste this into ChatGPT with product artwork.\n- Avoid: {', '.join(HARD_AVOID)}"
    with _card("Preview", "Copy this prompt template or save it as a pack."):
        _copy_button(preview, f"template-{selected}", "Copy Template")
        st.text_area("Template preview", value=preview, height=320, key="mf-template-preview", label_visibility="collapsed")
        if st.button("Save as pack", use_container_width=True, key="mf-save-template"):
            pack = {
                "full_prompt": preview,
                "strategy": selected,
                "input_payload": {"product_name": selected, "product_handle": "", "country": "", "ad_format": selected, "funnel_stage": "", "edition_stage": "", "primary_angle": "", "secondary_angles": []},
                "generated_at": _now_iso(),
            }
            try:
                saved = supabase_backend.save_ads_copy_pack(_pack_payload(pack), created_by="marketing_factory")
                st.success(f"Saved template pack {saved.get('id')}.")
                _load_saved_packs.clear()
            except Exception:
                st.error("Template could not be saved. You can still copy or download it.")


def _render_saved_packs_tab():
    st.subheader("Saved Packs")
    st.caption("Saved prompt/copy packs attached to products.")
    action_cols = st.columns([1, 1, 2])
    if action_cols[0].button("Load Saved Packs", use_container_width=True, key="mf-load-saved-packs"):
        st.session_state["mf_saved_packs_loaded"] = True
    if action_cols[1].button("Refresh Packs", use_container_width=True, key="mf-refresh-saved-packs"):
        _load_saved_packs.clear()
        st.session_state["mf_saved_packs_loaded"] = True
    if not st.session_state.get("mf_saved_packs_loaded"):
        st.info("Click Load Saved Packs when you need an existing prompt pack.")
        return
    packs = _load_saved_packs(limit=50)
    if not packs:
        st.warning("Saved packs are unavailable or empty. You can still generate, copy, and download a new pack.")
        return
    table = [
        {
            "created_at": _format_time(row.get("created_at")),
            "product title": row.get("product_title"),
            "product handle": row.get("product_handle"),
            "country": row.get("country"),
            "ad format": row.get("ad_format"),
            "funnel stage": row.get("funnel_stage"),
            "edition stage": row.get("edition_stage"),
            "angle": row.get("primary_angle"),
            "created_by": row.get("created_by"),
            "status": row.get("status") or "Draft",
        }
        for row in packs
    ]
    st.dataframe(table, hide_index=True, use_container_width=True, height=300)
    for row in packs[:20]:
        label = f"{_format_time(row.get('created_at'))} - {row.get('product_title') or 'Untitled'} - {row.get('status') or 'Draft'}"
        with st.expander(label):
            prompt = row.get("generated_prompt") or ""
            _copy_button(prompt, f"saved-{row.get('id')}", "Copy")
            action_cols = st.columns(4)
            action_cols[0].download_button("Download Markdown", data=prompt.encode("utf-8"), file_name="saved-marketing-pack.md", mime="text/markdown", use_container_width=True, key=f"saved-md-{row.get('id')}")
            action_cols[1].download_button("Download JSON", data=json.dumps(dict(row), indent=2, default=_json_default).encode("utf-8"), file_name="saved-marketing-pack.json", mime="application/json", use_container_width=True, key=f"saved-json-{row.get('id')}")
            if action_cols[2].button("Mark Ready", use_container_width=True, key=f"saved-ready-{row.get('id')}"):
                supabase_backend.update_ads_copy_pack_status(row.get("id"), "Ready")
                _load_saved_packs.clear()
                st.rerun()
            if action_cols[3].button("Mark Needs Review", use_container_width=True, key=f"saved-review-{row.get('id')}"):
                supabase_backend.update_ads_copy_pack_status(row.get("id"), "Needs Review")
                _load_saved_packs.clear()
                st.rerun()
            st.text_area("Prompt", value=prompt, height=220, key=f"saved-text-{row.get('id')}", label_visibility="collapsed")


def _render_quality_tab():
    st.subheader("Quality Checklist")
    st.caption("Use this before anything goes into Meta Ads Manager.")
    checklist_text = "\n".join(f"- {item}" for item in QUALITY_CHECKS)
    _copy_button(checklist_text, "quality-checklist", "Copy Checklist")
    cols = st.columns(2)
    for index, item in enumerate(QUALITY_CHECKS):
        cols[index % 2].checkbox(item, key=f"mf-quality-{_safe_key(item)}")


def render_page():
    started = time.perf_counter()
    _inject_styles()
    _render_header()
    tab_names = [
        "Ad Builder",
        "Meta Signals",
        "Winning Angles",
        "Prompt Library",
        "Saved Packs",
        "Quality Checklist",
    ]
    requested_tab = st.session_state.pop("mf_requested_tab", None)
    if requested_tab in tab_names:
        st.session_state["mf_active_tab"] = requested_tab
    active_tab = st.radio(
        "Marketing Factory section",
        tab_names,
        horizontal=True,
        label_visibility="collapsed",
        key="mf_active_tab",
    )
    if active_tab == "Ad Builder":
        _render_ad_builder()
    elif active_tab == "Meta Signals":
        _render_meta_intelligence_tab()
    elif active_tab == "Winning Angles":
        _render_winning_angles_tab()
    elif active_tab == "Prompt Library":
        _render_prompt_library_tab()
    elif active_tab == "Saved Packs":
        _render_saved_packs_tab()
    elif active_tab == "Quality Checklist":
        _render_quality_tab()
    print(f"marketing_factory_shell_ms={int((time.perf_counter() - started) * 1000)}")
