-- Explicit administrative cursor and limit changes. No product data changes on install.
BEGIN;
ALTER TABLE edition_cursor_overrides ADD COLUMN previous_limit integer;
ALTER TABLE edition_cursor_overrides ADD COLUMN next_limit integer;

CREATE FUNCTION public.override_edition_cursor(p_handle text,p_run uuid,p_expected integer,p_next integer,
 p_request uuid,p_actor uuid,p_expected_limit integer,p_limit integer) RETURNS jsonb
LANGUAGE plpgsql SET search_path=public,pg_temp AS $$
DECLARE p edition_products%ROWTYPE; r edition_runs%ROWTYPE; a edition_cursor_overrides%ROWTYPE;
 gid text; units integer;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM os_users WHERE id=p_actor AND role='admin' AND is_active
 AND COALESCE(account_status,'active')<>'removed') THEN RAISE EXCEPTION 'Active administrator required'; END IF;
 IF p_request IS NULL OR p_run IS NULL OR p_expected IS NULL OR p_next IS NULL
 OR p_expected_limit IS NULL OR p_limit IS NULL THEN RAISE EXCEPTION 'Complete override identity required'; END IF;
 IF p_limit NOT BETWEEN 1 AND 100 OR p_next NOT BETWEEN 1 AND p_limit+1
 THEN RAISE EXCEPTION 'Number must be within the edition limit (or the terminal sold-out number)'; END IF;
 SELECT COALESCE(NULLIF(shopify_product_gid,''),shopify_product_id) INTO STRICT gid
 FROM edition_products WHERE shopify_handle=p_handle;
 PERFORM pg_advisory_xact_lock(hashtextextended(gid,0));
 SELECT * INTO STRICT p FROM edition_products WHERE shopify_handle=p_handle FOR UPDATE;
 SELECT * INTO a FROM edition_cursor_overrides WHERE id=p_request;
 IF FOUND THEN
   IF a.run_id<>p_run OR a.next_number<>p_next OR a.previous_number<>p_expected OR a.actor_id<>p_actor
   OR a.previous_limit IS DISTINCT FROM p_expected_limit OR a.next_limit IS DISTINCT FROM p_limit
   OR NOT EXISTS(SELECT 1 FROM edition_runs WHERE id=a.run_id AND edition_product_id=p.id)
   THEN RAISE EXCEPTION 'Submission identity reused with different values'; END IF;
   RETURN to_jsonb(a);
 END IF;
 SELECT * INTO STRICT r FROM edition_runs WHERE id=p.active_edition_run_id FOR UPDATE;
 IF r.id<>p_run OR r.edition_product_id IS DISTINCT FROM p.id
 OR p.next_edition_number IS DISTINCT FROM p_expected OR p.edition_total IS DISTINCT FROM p_expected_limit
 THEN RAISE EXCEPTION 'Edition changed; refresh before saving'; END IF;
 IF r.status IN ('expired','pending_sync','archived','closed')
 THEN RAISE EXCEPTION 'Release is not available for override'; END IF;
 SELECT count(*) INTO units FROM edition_orders WHERE edition_run_id=r.id AND identity_enforced
 AND allocation_valid AND COALESCE(status,'') NOT IN ('voided','refunded','cancelled','superseded');
 INSERT INTO edition_cursor_overrides(id,run_id,actor_id,previous_number,next_number,duplicate_acknowledged,previous_limit,next_limit)
 VALUES(p_request,r.id,p_actor,p_expected,p_next,true,p_expected_limit,p_limit);
 PERFORM set_config('sports_cave.cursor_action','override',true);
 UPDATE edition_runs SET manual_override_id=p_request,next_edition_number=p_next,edition_total=p_limit,
 allocation_baseline_sold_count=greatest(0,COALESCE(p.sold_count,0)-units),sync_attempts=0,
 sync_retry_at=now(),sync_error='',updated_at=now() WHERE id=r.id;
 UPDATE edition_products SET manual_override_id=p_request,next_edition_number=p_next,edition_total=p_limit,
 remaining_count=CASE WHEN p_limit=p_expected_limit THEN remaining_count ELSE greatest(0,p_limit-sold_count) END,
 sold_out=(sold_count>=p_limit OR p_next>p_limit),is_sold_out=(sold_count>=p_limit OR p_next>p_limit),
 metafields_sync_status='Pending',last_metafield_error='',updated_at=now() WHERE id=p.id;
 INSERT INTO edition_version_audit(run_id,actor_id,action,before_state,after_state,reason)
 VALUES(r.id,p_actor,'NEXT NUMBER OVERRIDE',to_jsonb(p),jsonb_build_object('next',p_next,'limit',p_limit,'request',p_request),
 'Explicit administrator save; historical sales, orders and certificates retained');
 RETURN (SELECT to_jsonb(x) FROM edition_cursor_overrides x WHERE id=p_request);
END $$;
REVOKE ALL ON FUNCTION public.override_edition_cursor(text,uuid,integer,integer,uuid,uuid,integer,integer) FROM PUBLIC,anon,authenticated;

-- Backwards compatible API: explicit administrator action itself authorises reuse.
CREATE OR REPLACE FUNCTION public.override_edition_cursor(p_handle text,p_run uuid,p_expected integer,p_next integer,
 p_request uuid,p_actor uuid,p_ack boolean) RETURNS jsonb LANGUAGE plpgsql SET search_path=public,pg_temp AS $$
DECLARE total integer; a edition_cursor_overrides%ROWTYPE;
BEGIN
 SELECT * INTO a FROM edition_cursor_overrides WHERE id=p_request;
 IF FOUND AND a.previous_limit IS NOT NULL THEN total:=a.previous_limit;
 ELSE SELECT edition_total INTO STRICT total FROM edition_products WHERE shopify_handle=p_handle; END IF;
 RETURN public.override_edition_cursor(p_handle,p_run,p_expected,p_next,p_request,p_actor,total,total);
END $$;
COMMIT;
