-- Authorised metadata-only repair. No allocator, certificate generation or dispatch.
BEGIN;
SET LOCAL lock_timeout='15s';
DO $repair$
DECLARE
 o shopify_orders%ROWTYPE;
 l shopify_order_lines%ROWTYPE;
 e edition_orders%ROWTYPE;
 p edition_products%ROWTYPE;
 label text := 'Unframed / M - 30 × 45 cm (11.8 × 17.7 in)';
 repaired_lines jsonb;
 shipping_patch jsonb;
BEGIN
 SELECT * INTO STRICT p FROM edition_products WHERE id=723 FOR UPDATE;
 SELECT * INTO STRICT o FROM shopify_orders WHERE shopify_order_id='gid://shopify/Order/18924580208947' FOR UPDATE;
 SELECT * INTO STRICT l FROM shopify_order_lines WHERE shopify_order_id=o.shopify_order_id AND shopify_line_item_id='gid://shopify/LineItem/50761092759859' FOR UPDATE;
 SELECT * INTO STRICT e FROM edition_orders WHERE shopify_order_id=o.shopify_order_id AND shopify_line_item_id=l.shopify_line_item_id FOR UPDATE;
 IF o.order_name <> '#SC3232' OR o.customer_name <> 'Daniel Marshall'
   OR l.product_title <> 'Tom Brady Motivational Quote Art' OR l.quantity <> 1 OR l.sku <> 'TBRADYA3'
   OR e.id <> 608 OR e.edition_number <> 1 OR e.edition_total <> 100
   OR e.shopify_product_gid <> p.shopify_product_gid OR p.shopify_handle <> 'tom-brady-further-to-go'
   OR (SELECT count(*) FROM shopify_orders WHERE regexp_replace(shopify_order_id,'^.*/','')='18924580208947') <> 1
   OR (SELECT count(*) FROM shopify_order_lines WHERE regexp_replace(shopify_line_item_id,'^.*/','')='50761092759859') <> 1 THEN
   RAISE EXCEPTION 'SC3232 identity/allocation differs; repair aborted';
 END IF;
 IF EXISTS(SELECT 1 FROM audit_logs WHERE event_type='order_variant_metadata_repair' AND entity_id='sc3232-medium-unframed-standard-20261006') THEN
   IF l.variant_title <> label OR o.raw_json->>'shipping_method' <> 'Standard Shipping' THEN
     RAISE EXCEPTION 'Previously repaired metadata changed; review required';
   END IF;
   RETURN;
 END IF;
 UPDATE shopify_order_lines SET variant_title=label,
   raw_json=raw_json || jsonb_build_object('variant_title',label),updated_at=now() WHERE id=l.id;
 -- The certificate/fulfilment ledger also carries descriptive variant metadata.
 UPDATE edition_orders SET variant_title=label,updated_at=now() WHERE id=e.id;
 SELECT jsonb_agg(CASE WHEN item->>'shopify_line_item_id'=l.shopify_line_item_id
     THEN item || jsonb_build_object('variant_title',label) ELSE item END ORDER BY ordinal)
 INTO repaired_lines FROM jsonb_array_elements(o.raw_json->'line_items') WITH ORDINALITY t(item,ordinal);
 shipping_patch := jsonb_build_object('shipping_method','Standard Shipping',
   'shipping_carrier',coalesce(o.raw_json->>'shipping_carrier',o.raw_json->>'shipping_method'),
   '_fulfilment_shipping_override',jsonb_build_object('action_id','sc3232-medium-unframed-standard-20261006',
     'source_method',o.raw_json->>'shipping_method','reason','Operator confirmed Standard Shipping','at',now()));
 UPDATE shopify_orders SET raw_json=jsonb_set(raw_json,'{line_items}',repaired_lines) || shipping_patch,
   raw=jsonb_set(coalesce(raw,'{}'::jsonb),'{line_items}',repaired_lines) || shipping_patch,updated_at=now()
 WHERE shopify_order_id=o.shopify_order_id;
 IF (SELECT to_jsonb(ep) FROM edition_products ep WHERE id=p.id) <> to_jsonb(p)
   OR (SELECT to_jsonb(eo)-'variant_title'-'updated_at' FROM edition_orders eo WHERE id=e.id)
      <> to_jsonb(e)-'variant_title'-'updated_at' THEN
   RAISE EXCEPTION 'Edition invariants changed; rolling back';
 END IF;
 INSERT INTO audit_logs(event_type,entity_type,entity_id,shopify_order_id,shopify_line_item_id,
   shopify_handle,old_value,new_value,reason,actor,source)
 VALUES('order_variant_metadata_repair','shopify_order_line','sc3232-medium-unframed-standard-20261006',
   o.shopify_order_id,l.shopify_line_item_id,p.shopify_handle,
   jsonb_build_object('variant_title',l.variant_title,'shipping_method',o.raw_json->>'shipping_method'),
   jsonb_build_object('variant_title',label,'shipping_method','Standard Shipping','carrier','Australia Post',
     'edition_unchanged',e.edition_number,'next_unchanged',p.next_edition_number,
     'sold_unchanged',p.sold_count,'remaining_unchanged',p.remaining_count),
   'Authorised SC3232 Medium Unframed / Standard Shipping repair from Shopify custom attributes and operator confirmation',
   'authorised_operator','targeted_repair');
END $repair$;
COMMIT;
