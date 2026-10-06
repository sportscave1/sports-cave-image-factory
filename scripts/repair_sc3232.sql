-- Explicitly authorised order-line mapping and allocation. No schema changes.
BEGIN;
SET LOCAL lock_timeout = '15s';
SET LOCAL statement_timeout = '60s';
DO $repair$
DECLARE
 p edition_products%ROWTYPE;
 o shopify_orders%ROWTYPE;
 l shopify_order_lines%ROWTYPE;
 a jsonb;
 after_p edition_products%ROWTYPE;
 reason_text text := 'Authorised canonical mapping: #SC3232 Tom Brady Motivational Quote Art / TBRADYA3 -> Tom Brady — Further To Go (tom-brady-further-to-go), followed by late edition allocation.';
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('gid://shopify/Product/15399569064243',0));
 SELECT * INTO STRICT p FROM edition_products WHERE id=723 FOR UPDATE;
 SELECT * INTO STRICT o FROM shopify_orders WHERE shopify_order_id='gid://shopify/Order/18924580208947' FOR UPDATE;
 SELECT * INTO STRICT l FROM shopify_order_lines WHERE shopify_order_id=o.shopify_order_id
   AND shopify_line_item_id='gid://shopify/LineItem/50761092759859' FOR UPDATE;
 IF p.shopify_handle <> 'tom-brady-further-to-go' OR p.shopify_product_gid <> 'gid://shopify/Product/15399569064243'
   OR p.edition_total <> 100 OR o.order_name <> '#SC3232' OR o.customer_name <> 'Daniel Marshall'
   OR upper(o.financial_status) <> 'PAID' OR o.cancelled_at IS NOT NULL
   OR l.product_title <> 'Tom Brady Motivational Quote Art' OR l.sku <> 'TBRADYA3' OR l.quantity <> 1
   OR coalesce(l.shopify_product_id,'') NOT IN ('','gid://shopify/Product/15399569064243')
   OR coalesce(l.shopify_handle,'') NOT IN ('','tom-brady-further-to-go') THEN
   RAISE EXCEPTION 'SC3232 verified identity changed; no changes applied';
 END IF;
 -- Existing canonical allocator validates replay identities, reservations and collisions,
 -- locks the run and consumes CURRENT next_edition_number, never a guessed number.
 SELECT result INTO STRICT a FROM allocate_edition_line_units_atomic(
   'shopify',o.shopify_order_id,l.shopify_line_item_id,p.shopify_product_gid,l.quantity,
   o.shopify_order_id,o.order_name,l.shopify_line_item_id,'',p.product_title,
   coalesce(l.variant_title,''),l.sku,o.customer_name,coalesce(o.customer_email,o.email,''),'assigned') result;
 IF (a->>'was_created')::boolean THEN
   -- Existing persistent per-line canonical mapping. Immutable source title/raw stay intact.
   UPDATE shopify_order_lines SET shopify_product_id=p.shopify_product_gid,
     shopify_handle=p.shopify_handle,assignment_status='Assigned',last_error='',updated_at=now()
   WHERE id=l.id;
   SELECT * INTO STRICT after_p FROM edition_products WHERE id=p.id;
   INSERT INTO edition_adjustments(edition_product_id,edition_run_id,shopify_product_id,shopify_handle,
     old_next_edition_number,new_next_edition_number,old_edition_total,new_edition_total,source,reason)
   VALUES(p.id,p.active_edition_run_id,p.shopify_product_gid,p.shopify_handle,
     p.next_edition_number,after_p.next_edition_number,p.edition_total,p.edition_total,'admin_late_product',
     jsonb_build_object('action_id','sc3232-authorised-canonical-mapping-20261006','reason',reason_text,
       'order',o.order_name,'order_id',o.shopify_order_id,'line_id',l.shopify_line_item_id,
       'sku',l.sku,'source_title',l.product_title,'canonical_product',p.product_title,
       'edition_product_id',p.id,'handle',p.shopify_handle,'edition_number',a->'allocation'->'edition_number',
       'old_state',l.assignment_status,'old_product_id',l.shopify_product_id,
       'before',jsonb_build_object('next',p.next_edition_number,'sold',p.sold_count,'remaining',p.remaining_count),
       'after',jsonb_build_object('next',after_p.next_edition_number,'sold',after_p.sold_count,'remaining',after_p.remaining_count),
       'timestamp',now())::text);
 END IF;
END $repair$;
COMMIT;
