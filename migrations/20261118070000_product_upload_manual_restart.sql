-- A fresh delivery ID invalidates old desktop tabs/receipts without replacing the upload.
ALTER TABLE public.product_upload_staff_jobs ADD COLUMN IF NOT EXISTS dispatch_id uuid;
CREATE UNIQUE INDEX IF NOT EXISTS product_upload_dispatch_id
    ON public.product_upload_staff_jobs(dispatch_id) WHERE dispatch_id IS NOT NULL;
