"""Source-preserving Creative Refresh contract; no New Ads policy or provider writes."""
import hashlib
import json

VERSION = 'SOURCE WINNER PRESERVATION V1'
AUTHORITY = '''WINNER_REFERENCE (WINNER_IE, WINNER_AD or the corresponding WINNER_CARD_N) controls the recognisable setting, architecture, wall treatment, defining objects, composition, camera direction, lighting character, product prominence and physical scale, advertising copy, footer presentation, CTA and valid offer.
CANONICAL_PRODUCT controls only the exact edition design and verified physical product, including its matching frame variant. Never reconstruct the design from the winner. Never copy the canonical photograph’s external background.
Inspect the actual winner and canonical image attachments before resolving any test. URLs, product titles and metadata alone are not image inspection. When mapping, frame variant, artwork or source format is ambiguous, request selection of the correct product/reference; never guess or require a new manual upload when verified image bytes are already accessible.
Start every alternative independently from the original source winner, never from another alternative. Keep every component locked except ONE declared test component. Do not rotate rooms, camera directions, footer sentences or copy fields. No mandated right/front/left changes or room diversity. Preserve source dimensions/aspect ratio, carousel roles and card order.
For a written-copy-only test reuse the original image bytes. For a local on-image-text test use a supported local edit/composite and preserve unaffected regions. If only a full generative redraw is available, disclose secondary differences; never claim exact preservation. Do not silently substitute a redraw for a copy-only test.
Preserve valid offers; flag expired, unverifiable or conflicting offers and inaccurate product details before execution. Correcting a product or offer conflict is not an unreported second test. Resolve it explicitly before producing alternatives.
Do not describe these untested alternatives as improvements or proven winners. No publication or live campaign edits.'''


def active(value):
    return (value or {}).get('version') == VERSION


def build_plan(context, campaign_type, product, category, seed, references, identity):
    references=[dict(r) for r in references]
    canonical=(context or {}).get('canonical_reference') or {}
    for ref in references:
        if ref.get('label')=='CANONICAL_PRODUCT':
            ref.update({**canonical,'authority':'Exact edition design and verified matching physical variant only'})
    return dict(version=VERSION, run_id=hashlib.sha256((identity+str(seed)).encode()).hexdigest()[:24],
                identity_hash=identity, product=product, category=category, campaign_type=campaign_type,
                seed=str(seed), references=references, styles=[], recent_styles=[],
                visual_analysis='Pending actual winner and canonical attachment inspection; no replacement scene or test is resolved yet.',
                preservation=AUTHORITY,
                **({'carousel_contract':'COLLECTIVE WINNER CAROUSEL V1'} if campaign_type=='Carousel' else {}))


def build_prompt(ads, product, category, country, campaign_type, url, winner, selected, metadata):
    source=winner.get('source_winner') or {}
    refs=selected['references']
    identity=dict(product_name=product,category=category,country=country,campaign_type=campaign_type,
                  workflow_mode=ads.ADS_WORKFLOW_MODE_CREATIVE_REFRESH,creative_refresh_context=winner,product_url=url)
    if campaign_type=='Carousel':
        template=ads.build_carousel_copy_csv(identity,template=True)
        count=f"ONE refreshed {len(refs)}-CARD carousel with original ordered cards. Select one test component for the package; unchanged cards reuse their source images. Keep the existing five shared-copy rows as compatibility slots, repeating unchanged source copy where appropriate."
    elif campaign_type=='Instant Experience':
        template=ads.build_instant_experience_copy_csv(identity,blank=True)
        count='THREE refresh alternatives; one copy record and one associated image per alternative, variation=1, output_mode=winner_refinement.'
    else:
        template=ads.build_standard_ads_csv(product_name=product)
        count='THREE refresh alternatives using the existing three-row standard CSV.'
    return f'''{VERSION}
SPORTS CAVE — CREATIVE REFRESH
Product: {product}
Category: {category}
Market: {country}
Campaign format: {campaign_type}
Product page: {url}
{AUTHORITY}

SOURCE COPY — retain verbatim unless this exact field is the selected test:
Primary text: {winner.get('winning_primary_text','')}
Written headline: {winner.get('winning_headline','')}
Description: {source.get('description','Read from source evidence; do not invent')}
CTA: {source.get('cta','Read from source evidence; do not substitute a default')}
Source evidence: {json.dumps(source,ensure_ascii=False,default=str)}
Verified product metadata: {json.dumps(metadata or {},ensure_ascii=False,default=str)}
Image reference manifest: {json.dumps(refs,ensure_ascii=False,default=str)}
Canonical attachment: {json.dumps(winner.get('canonical_reference') or {},ensure_ascii=False,default=str)}
Use the actual accessible labelled images supplied by the reference panel/attachments. Retrieve accessible references before requesting missing uploads. Confirm CANONICAL_PRODUCT is the exact mapped edition and frame variant; it is not an extra output image or Carousel card.

OUTPUT COUNT: {count}
If a labelled reference is missing, list every missing labelled image and stop. One winning image cannot stand in for 5 different carousel cards. OS has not analysed winner pixels.
Inspect first; then record in existing refresh_executions notes for each alternative/card: position, winner_reference, reference_inspected, canonical_inspected, observations, scene, role, keep (all preserved components), change (one concrete test), improvement (why worth testing, a hypothesis), secondary_differences (explicitly 'none' when none), changed_components (exactly one selected component), image_action ('reuse_original', 'local_edit' or 'redraw'), unresolved_conflicts (empty only after checking product/offer conflicts), and image_prompt. Do not invent inspection completion. Unchanged Carousel cards use changed_components=[] and image_action='reuse_original'; the whole carousel still has only one intended test component.
Compare observations with the plan: lock every non-test component. Populate all required CSV fields with unchanged source values except the declared test field. Repeated headlines, primary text, descriptions, CTAs, footer text and image bytes are valid preservation, not quality failures. Do not apply New Ads headline selection or description rewriting to Refresh.
Legacy IE route IDs remain unchanged for import/export compatibility. Their historic Right/Centre/Left labels identify storage slots only, NOT camera assignments. Display Refresh 1, Refresh 2 and Refresh 3 in review notes. Never imply that a route label changed the observed source camera.
Every image_prompt must identify its original winner reference and CANONICAL_PRODUCT, list locked components, the single test, execution method and any secondary differences. Copy-only briefs explicitly say reuse original bytes, no image generation. Source footer wording, height, typography, colours, separator and CTA remain unchanged unless that single footer component is selected for testing. Do not apply current New Ads footer banks to the winner.
Return existing copy fields, existing notes, the completed CSV and actual image download links in existing order. For reused originals, provide that accessible original file; do not regenerate to manufacture a download. Report inaccessible files honestly. No alternative copy menus or extra images.

Preserve CSV columns, route IDs, row order and encoding.
EXACT CSV TEMPLATE
{template.decode('utf-8-sig')}
'''


def execution_issues(executions, selected, campaign_type):
    count=len(selected.get('references',[])) if campaign_type=='Carousel' else 3
    if not isinstance(executions,list) or len(executions)!=count:
        return [f'Record {count} source-preserving execution notes before marking ready.']
    issues=[]
    carousel_changes=[]
    for i,row in enumerate(executions,1):
        if not isinstance(row,dict):
            issues.append(f'Refresh {i}: invalid execution record.');continue
        expected=f'WINNER_CARD_{i}' if campaign_type=='Carousel' else ('WINNER_IE' if campaign_type=='Instant Experience' else 'WINNER_AD')
        if row.get('position')!=i or row.get('winner_reference')!=expected:
            issues.append(f'Refresh {i}: preserve the source reference and card order.')
        if row.get('reference_inspected') is not True or row.get('canonical_inspected') is not True:
            issues.append(f'Refresh {i}: inspect actual winner and canonical images first.')
        if row.get('unresolved_conflicts') != []:
            issues.append(f'Refresh {i}: resolve or explicitly flag product/offer conflicts before execution.')
        fields=('observations','keep','change','improvement','secondary_differences','image_prompt')
        if any(not row.get(k) for k in fields):
            issues.append(f'Refresh {i}: record preserved components, one change, rationale and secondary differences.')
        changes=row.get('changed_components')
        if not isinstance(changes,list) or len(changes)!=(0 if campaign_type=='Carousel' and row.get('image_action')=='reuse_original' and not changes else 1):
            issues.append(f'Refresh {i}: exactly one intended test component is allowed.')
        if not isinstance(changes,list) or any(not isinstance(c,str) or not c.strip() for c in changes):
            issues.append(f'Refresh {i}: name each test component explicitly.'); changes=[]
        carousel_changes.extend(changes)
        refs=selected.get('references') or []
        ref=refs[i-1] if campaign_type=='Carousel' and i<=len(refs) else {}
        for field in ('scene','role'):
            if ref.get(field) and row.get(field)!=ref[field] and field not in changes:
                issues.append(f'Refresh {i}: source {field} changed without being the declared test.')
        brief=str(row.get('image_prompt') or '')
        if expected not in brief or 'CANONICAL_PRODUCT' not in brief:
            issues.append(f'Refresh {i}: identify both winner and canonical authority in its image brief.')
        if row.get('image_action') not in ('reuse_original','local_edit','redraw'):
            issues.append(f'Refresh {i}: specify the image execution method.')
        if changes and set(changes)<= {'headline','primary_text','description'} and row.get('image_action')!='reuse_original':
            issues.append(f'Refresh {i}: copy-only tests must reuse the original image.')
        if row.get('image_action')=='redraw' and str(row.get('secondary_differences','')).lower()=='none':
            issues.append(f'Refresh {i}: a redraw cannot claim exact preservation; disclose secondary differences.')
    if campaign_type=='Carousel' and len(carousel_changes)!=1:
        issues.append('Carousel refresh must declare one test component across the source package.')
    return issues


def copy_issues(rows, executions, originals):
    """Reject undeclared changes to known source copy; unknown evidence stays manual."""
    issues=[]
    for i,(row,original) in enumerate(zip(rows,originals)):
        note=executions[i] if i<len(executions) and isinstance(executions[i],dict) else {}
        changed=note.get('changed_components') or []
        for field in ('primary_text','headline','description','cta'):
            if original.get(field) and field not in changed and row.get(field)!=original[field]:
                issues.append(f'Refresh {i+1}: preserve source {field}; it is not the declared test.')
    return issues
