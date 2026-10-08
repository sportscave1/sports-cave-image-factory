CREATE ROLE anon; CREATE ROLE authenticated;
CREATE TABLE os_users(id uuid PRIMARY KEY,role text,is_active boolean,account_status text);
CREATE TABLE edition_products(id bigserial PRIMARY KEY,shopify_product_id text,shopify_product_gid text,shopify_handle text UNIQUE,
 product_title text,edition_total integer DEFAULT 100,next_edition_number integer DEFAULT 1,last_assigned_edition integer DEFAULT 0,
 sold_count integer DEFAULT 0,remaining_count integer DEFAULT 100,active boolean DEFAULT true,is_active boolean DEFAULT true,
 sold_out boolean DEFAULT false,is_sold_out boolean DEFAULT false,active_edition_run_id uuid,edition_name text,
 allow_counter_history_override boolean,metafields_sync_status text,last_metafield_error text,metafields_synced_at timestamptz,
 edition_status text,edition_display_text text,featured_image_url text,updated_at timestamptz DEFAULT now());
CREATE TABLE shopify_orders(shopify_order_id text PRIMARY KEY,raw_json jsonb DEFAULT '{}',created_at timestamptz DEFAULT now());
CREATE TABLE shopify_products(handle text,shopify_product_id text,shopify_product_gid text,status text,admin_url text,online_store_url text,featured_image_url text,image_url text);
CREATE TABLE shopify_variants(shopify_product_id text,sku text);
CREATE TABLE edition_orders(id bigserial PRIMARY KEY,shopify_order_id text,shopify_order_name text,shopify_line_item_id text,
 shopify_product_id text,shopify_variant_id text,shopify_handle text,product_title text,edition_run_id uuid,edition_name text,
 edition_number integer,edition_total integer,allocation_index integer,allocation_key text,quantity integer,variant_title text,sku text,
 customer_name text,customer_email text,shopify_customer_name text,shopify_customer_email text,assigned_at timestamptz,
 certificate_status text,status text,source text,updated_at timestamptz DEFAULT now());
CREATE TABLE certificates(id serial,edition_order_id text,certificate_file_url text);
CREATE TABLE audit_logs(id serial,event_type text,entity_type text,entity_id text,shopify_order_id text,shopify_line_item_id text,shopify_handle text,old_value jsonb,new_value jsonb,reason text,actor text,source text);
