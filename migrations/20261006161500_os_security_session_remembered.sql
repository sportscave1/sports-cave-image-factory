ALTER TABLE os_security_sessions
ADD COLUMN IF NOT EXISTS remembered boolean NOT NULL DEFAULT false;
