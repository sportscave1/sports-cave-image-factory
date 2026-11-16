"""Copy Upload Prompt: concise shared generator for new and saved uploads."""
from product_upload_intake import mode


def build(selected, filename='', *, source=None, metadata=None, app_module=None, load=None, automatic=False):
    mode(selected)
    if automatic and selected == 'DRAFT':
        selected = 'LIVE'
    smart = selected == 'SMART'
    details = metadata or {}
    if smart:
        if details.get('refresh_target_pending'):
            return ('The earlier PSD revision requested a Shopify refresh. The current revision needs its exact '
                    'existing Shopify product ID verified in Design Studio. Report the missing refresh target '
                    'and pause Shopify and PSD mapping at this step. Preserve the saved Dropbox images.')
        from product_upload_intake import stored_mode
        selected = stored_mode(selected, details)
        if selected == 'UPDATE':
            import re
            if not re.fullmatch(r'gid://shopify/Product/[1-9][0-9]*', str(details.get('shopify_product_id') or '')):
                raise ValueError('A refresh needs an exact existing Shopify product ID.')
    if app_module is None:
        import product_upload_prompt_core as app_module
    import prompt_store
    from product_upload_compact import build as compact, template_additions
    app = app_module
    load = load or prompt_store.get_prompt
    kind = {'DRAFT': app.PRODUCT_UPLOAD_NEW_TYPE, 'LIVE': app.PRODUCT_UPLOAD_LIVE_TYPE,
            'UPDATE': app.PRODUCT_UPLOAD_EXISTING_TYPE}[selected]
    cfg = app.product_upload_operation_config(kind)
    # Read existing editable templates to retain custom business requirements.
    # Their old SOP wrappers/appendices are not exported to the clipboard.
    legacy_metadata = {'product_name': 'Identify the product from the supplied website images and verified research'}
    default = app.get_product_upload_prompt(legacy_metadata,
        update_existing=cfg['update_existing'], publication_mode=cfg['publication_mode'])
    saved = load(cfg['prompt_id'], default, seed_default=False)
    patched = app.apply_product_upload_prompt_updates(saved, legacy_metadata,
        update_existing=cfg['update_existing'], publication_mode=cfg['publication_mode'])
    baseline = app.apply_product_upload_prompt_updates(default, legacy_metadata,
        update_existing=cfg['update_existing'], publication_mode=cfg['publication_mode'])
    prompt = compact(selected, filename, source, details, template_additions(patched, baseline, automatic=automatic),
                     automatic=automatic)
    if not smart:
        return prompt
    import json
    manual_instruction = ('' if automatic else
                          'Submitting this Smart Upload prompt authorises the appropriate action below. No additional routine confirmation is needed. ')
    policy = (
        'SMART UPLOAD — CHOOSE THE ACTION FROM THE ARTWORK AND VERIFIED CATALOGUE\n'
        + manual_instruction
        + 'Check the operation tag and exact design version first. Reuse an already recorded result and resume partial work on the same product. '
        'Verify the design story against the catalogue before changing Shopify. A different moment, title or collector concept is a new product even when the athlete is the same. '
        'Only replace artwork when this is an improved version of the same design and the supplied exact Shopify product ID identifies its original. '
        'Similarity alone never authorises replacement. If an existing match is plausible but the identity or improvement is uncertain, report Needs attention and leave Shopify untouched.\n'
    )
    if selected == 'UPDATE':
        policy += ('Use the Update Existing instructions below for the exact linked product only. Preserve its ID, URL, options, variants, '
                   'sales history, edition history, counters, allocations and inventory. If it cannot be verified, stop this item without creating another product.\n')
    else:
        policy += ('Use Upload to Live below for a verified new design. If catalogue evidence suggests this is an existing-design refresh '
                   'without an exact supplied target, flag it for attention. Never create a duplicate or update an unlinked listing.\n')
    if details.get('intended_collections'):
        policy += 'Intended collections to verify: ' + json.dumps(details['intended_collections'], ensure_ascii=False) + '\n'
    return policy + '\n' + prompt
