-- Add visit identity separately from per-save capture identity. Existing history is retained.
ALTER TABLE public.wall_preview_events
 ADD COLUMN IF NOT EXISTS wall_preview_session_id uuid,
 ADD COLUMN IF NOT EXISTS visitor_id uuid,
 ADD COLUMN IF NOT EXISTS event_type text,
 ADD COLUMN IF NOT EXISTS active_seconds numeric(12,3) CHECK (active_seconds >= 0 AND active_seconds <= 86400);
ALTER TABLE public.wall_preview_events DROP CONSTRAINT IF EXISTS wall_preview_events_event_name_check;
ALTER TABLE public.wall_preview_events ADD CONSTRAINT wall_preview_events_event_name_check CHECK (event_name IN (
 'WallPreviewStarted','WallPreviewCameraOpened','WallPreviewGalleryOpened','WallPreviewPhotoCaptured',
 'WallPreviewPhotoUploaded','WallPreviewPhotoReady','WallPreviewArtworkDragged','WallPreviewFrameChanged',
 'WallPreviewSizeChanged','WallPreviewScaleStarted','WallPreviewScaleCompleted','WallPreviewQuickPreviewUsed',
 'WallPreviewConfirmed','WallPreviewDownloaded','WallPreviewShared','WallPreviewAddedToCart',
 'WallPreviewCheckoutStarted','WallPreviewPurchased','WallPreviewClosed','WallPreviewEmailCaptured',
 'WallPreviewCTAClick','WallPreviewActiveTime'));
CREATE INDEX IF NOT EXISTS wall_preview_visit_events ON public.wall_preview_events(wall_preview_session_id,occurred_at) WHERE wall_preview_session_id IS NOT NULL;
