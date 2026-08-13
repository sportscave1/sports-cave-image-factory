ALTER TABLE dashboard_tasks
    ADD COLUMN IF NOT EXISTS design_style TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'dashboard_tasks_design_style_valid'
          AND conrelid = 'dashboard_tasks'::regclass
    ) THEN
        ALTER TABLE dashboard_tasks
            ADD CONSTRAINT dashboard_tasks_design_style_valid
            CHECK (
                design_style IS NULL
                OR design_style IN (
                    'ultimate_moment',
                    'rivalry_faceoff',
                    'legends_jersey_display',
                    'nostalgic_tribute',
                    'motorsport_driver_car',
                    'minimalist_hero',
                    'championship_achievement',
                    'vintage_restoration',
                    'update_existing'
                )
            ) NOT VALID;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_dashboard_tasks_design_style_open
    ON dashboard_tasks(design_style, created_at DESC)
    WHERE status = 'open' AND section = 'New designs to complete';
