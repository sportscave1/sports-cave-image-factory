CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS prompt_templates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_key text UNIQUE NOT NULL,
    prompt_name text,
    module text,
    prompt_text text NOT NULL,
    source text DEFAULT 'supabase',
    updated_by text,
    updated_at timestamptz DEFAULT now(),
    created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS prompt_template_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_key text NOT NULL,
    old_prompt_text text,
    new_prompt_text text,
    updated_by text,
    created_at timestamptz DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_prompt_templates_key_unique
ON prompt_templates(prompt_key);

CREATE INDEX IF NOT EXISTS idx_prompt_template_versions_key
ON prompt_template_versions(prompt_key, created_at DESC);
