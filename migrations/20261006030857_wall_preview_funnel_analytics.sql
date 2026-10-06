-- Extend the existing ledger. Preserve previews, archive routes and historical events.
ALTER TABLE public.wall_preview_events ALTER COLUMN preview_id DROP NOT NULL;
ALTER TABLE public.wall_preview_events DROP CONSTRAINT IF EXISTS wall_preview_events_event_name_check;
ALTER TABLE public.wall_preview_events ADD CONSTRAINT wall_preview_events_event_name_check CHECK (event_name IN (
 'WallPreviewStarted','WallPreviewCameraOpened','WallPreviewGalleryOpened','WallPreviewPhotoCaptured',
 'WallPreviewPhotoUploaded','WallPreviewPhotoReady','WallPreviewArtworkDragged','WallPreviewFrameChanged',
 'WallPreviewSizeChanged','WallPreviewScaleStarted','WallPreviewScaleCompleted','WallPreviewQuickPreviewUsed',
 'WallPreviewConfirmed','WallPreviewDownloaded','WallPreviewShared','WallPreviewAddedToCart',
 'WallPreviewCheckoutStarted','WallPreviewPurchased','WallPreviewClosed','WallPreviewEmailCaptured'));
ALTER TABLE public.wall_preview_events
 ADD COLUMN IF NOT EXISTS client_preview_id uuid,
 ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'legacy',
 ADD COLUMN IF NOT EXISTS product_id text NOT NULL DEFAULT '',
 ADD COLUMN IF NOT EXISTS variant_id text NOT NULL DEFAULT '',
 ADD COLUMN IF NOT EXISTS product_handle text NOT NULL DEFAULT '',
 ADD COLUMN IF NOT EXISTS product_title text NOT NULL DEFAULT '',
 ADD COLUMN IF NOT EXISTS frame text NOT NULL DEFAULT '',
 ADD COLUMN IF NOT EXISTS size text NOT NULL DEFAULT '',
 ADD COLUMN IF NOT EXISTS unit text NOT NULL DEFAULT '',
 ADD COLUMN IF NOT EXISTS device_type text NOT NULL DEFAULT '',
 ADD COLUMN IF NOT EXISTS capture_source text NOT NULL DEFAULT '',
 ADD COLUMN IF NOT EXISTS page_url text NOT NULL DEFAULT '',
 ADD COLUMN IF NOT EXISTS referrer text NOT NULL DEFAULT '',
 ADD COLUMN IF NOT EXISTS utm_source text NOT NULL DEFAULT '',
 ADD COLUMN IF NOT EXISTS utm_medium text NOT NULL DEFAULT '',
 ADD COLUMN IF NOT EXISTS utm_campaign text NOT NULL DEFAULT '',
 ADD COLUMN IF NOT EXISTS utm_content text NOT NULL DEFAULT '',
 ADD COLUMN IF NOT EXISTS utm_term text NOT NULL DEFAULT '',
 ADD COLUMN IF NOT EXISTS elapsed_ms bigint,
 ADD COLUMN IF NOT EXISTS furthest_stage text NOT NULL DEFAULT '',
 ADD COLUMN IF NOT EXISTS order_id text,
 ADD COLUMN IF NOT EXISTS order_number text,
 ADD COLUMN IF NOT EXISTS quantity integer,
 ADD COLUMN IF NOT EXISTS line_revenue numeric(18,4),
 ADD COLUMN IF NOT EXISTS order_revenue numeric(18,4),
 ADD COLUMN IF NOT EXISTS currency text NOT NULL DEFAULT '';
CREATE UNIQUE INDEX IF NOT EXISTS wall_preview_event_retry ON public.wall_preview_events(session_id,event_key) WHERE source='storefront';
CREATE UNIQUE INDEX IF NOT EXISTS wall_preview_purchase_line ON public.wall_preview_events(event_key) WHERE source='shopify';
CREATE INDEX IF NOT EXISTS wall_preview_event_time ON public.wall_preview_events(occurred_at);
CREATE INDEX IF NOT EXISTS wall_preview_event_session ON public.wall_preview_events(session_id);
CREATE INDEX IF NOT EXISTS wall_preview_event_client ON public.wall_preview_events(client_preview_id,occurred_at);
CREATE INDEX IF NOT EXISTS wall_preview_event_product ON public.wall_preview_events(product_id,occurred_at);
ALTER TABLE public.wall_preview_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.wall_preview_events FROM PUBLIC,anon,authenticated;
