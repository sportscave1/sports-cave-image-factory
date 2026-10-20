"""Copy Upload Prompt: concise shared generator for new and saved uploads."""
from product_upload_intake import mode


def build(selected, filename='', *, source=None, metadata=None, app_module=None, load=None):
    mode(selected)
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
    return compact(selected, filename, source, metadata or {}, template_additions(patched, baseline))
