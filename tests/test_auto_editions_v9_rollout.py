from scripts.enable_auto_editions_v9 import PRODUCT, TARGETS, matches


def test_rollout_matches_all_seven_exact_order_line_units_and_rejects_mismatches():
    for expected in TARGETS.values():
        order, oid, line, variant, ordinal, edition = expected
        unit = dict(shopify_product_gid=PRODUCT, shopify_order_name=order,
                    shopify_order_id='gid://shopify/Order/'+oid,
                    shopify_line_item_id=line,
                    shopify_variant_id='gid://shopify/ProductVariant/'+variant,
                    unit_ordinal=ordinal, allocation_index=ordinal,
                    edition_number=edition, edition_total=100)
        assert matches(unit, expected)
        for key in unit:
            changed = dict(unit)
            changed[key] = 'different' if isinstance(unit[key], str) else unit[key]+1
            assert not matches(changed, expected), key
