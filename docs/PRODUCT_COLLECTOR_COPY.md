# Product collector-copy upgrade

## Trace and scope

The Product Uploads UI exports a ChatGPT/Shopify execution prompt; it does not
invoke a text-generation API or parse a generated title/description itself.
New and Existing use separate raw SOP constants in app.py:
NEW_SHOPIFY_PRODUCT_PROMPT (SOP 07B) and UPDATE_EXISTING_PRODUCT_PROMPT (SOP 07C).
Both pass through get_product_upload_prompt/build_product_upload_prompt and the
same apply_product_upload_prompt_updates transform. Saved Prompt Store overrides
also receive that final transform via render_copyable_prompt.

Old copy instructions required 90–130 words, two story paragraphs and a mandatory
bold scarcity close. They recurred in execution and QA sections, including
PRODUCT_UPLOAD_QA_CHECKLIST_PROMPT. The new title SOP favoured search-led
[Subject or Moment] Wall Art without the required em dash/design name.

product_collector_copy.py now owns the shared visible-copy policy. It removes
known conflicting visible-copy sections from the exported prompt, replaces legacy
length/checklist lines, and appends one authoritative, idempotent policy block.
Raw baseline SOP constants are retained for compatibility, but neither Product
Uploads entry point exports them without this transform. Saved custom copy rules
are explicitly superseded; their separate SEO and operational instructions remain.
Old prompts copied out of the app previously cannot be retroactively updated.

This preserves SEO meta title/description, handle, alt text, media, pricing,
variants, inventory, edition allocation, status, publishing and response contracts.
Existing Media Update Mode still preserves title/description unless a copy rewrite
or full standardisation is requested. Design Studio is unchanged.

The self-review is a prompt instruction, not a deterministic prose validator:
downstream model output still needs review. No new API, database schema or live
Shopify action was introduced.

## Validation

47 tests passed across collector copy, Product Upload prompts, saved Prompt Store
and shared image/video prompt blocks. Six representative research cases were sent
through the actual builder for BOTH modes (12 generated prompts), verifying the
same policy, retained research, SEO isolation and removal of old length/structure.
Repeated transforms are identical. Title/HTML previews satisfy the contract and
short-copy checks. Compilation and git diff --check also passed.

## Before / after previews

Before: the exported instructions demanded 90–130 words and exactly four
paragraphs with two story paragraphs, regardless of whether that much copy helped.
After: approximately 45–70 words, with stronger shorter copy permitted, and
subject-first em-dash titles. No mandatory generic closing slogan.

The following are authored review previews following the exported prompt rules,
not outputs from an external model API. Each fixture explicitly confirms a
100-edition worldwide run; real prompts must omit that claim without evidence.
The production resolver contains no athlete-specific cases. Historical facts in
these examples are supplied fixture research, not inferred from image composition.


### NBA single player

Nikola Jokic — The Joker Wall Art

<p><strong>Calm under pressure.</strong></p><p>Traffic everywhere. Jokić never rushed.</p><p>For Denver fans, that patience and control are the whole point. A reminder that the smartest player in the room never needed to be the loudest.</p><p>Limited to 100 worldwide.</p>

### NBA historical achievement

Wilt Chamberlain — 100 Point Game Wall Art

<p><strong>One night. One hundred.</strong></p><p>On 2 March 1962, Wilt Chamberlain scored 100 points.</p><p>Some numbers need no explanation. For the fans who know this one, it is a whole conversation—and a piece of basketball history worth keeping close.</p><p>Limited to 100 worldwide.</p>

### Australian motorsport

Casey Stoner — Crowned at Home Wall Art

<p><strong>Champion. On home soil.</strong></p><p>Phillip Island, 2011. Casey Stoner secured the world championship in front of Australia.</p><p>Winning was one thing. Watching him do it at home meant something else. For the fans who still feel that pride when they hear his name.</p><p>Limited to 100 worldwide.</p>

### Motorsport duo

Larry Perkins & Russell Ingall — Last to First Wall Art

<p><strong>Never count them out.</strong></p><p>Larry Perkins and Russell Ingall. A reminder of why you keep watching when a race turns against you.</p><p>For the fans who back their drivers through the setbacks, not just the celebrations. The fight back is what stays with you.</p><p>Limited to 100 worldwide.</p>

### Football

Lionel Messi — A Different Rhythm Wall Art

<p><strong>The game felt different.</strong></p><p>Watching Messi was never just about waiting for the score.</p><p>It was the anticipation every time the ball reached him. For the fans who stopped talking, leaned forward and refused to look away. Keep that feeling close.</p><p>Limited to 100 worldwide.</p>

### Cricket

Shane Warne — The Art of Spin Wall Art

<p><strong>Every ball held a question.</strong></p><p>With Warne, waiting for the next delivery was part of the pleasure.</p><p>For the cricket fans who loved the contest before the result—the patience, the doubt, the possibility of a wicket. That anticipation belongs in the memory.</p><p>Limited to 100 worldwide.</p>
