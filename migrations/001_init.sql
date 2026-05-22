CREATE TABLE IF NOT EXISTS jobs (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,
    url             TEXT NOT NULL UNIQUE,
    title           TEXT NOT NULL,
    company         TEXT,
    location        TEXT,
    posted_date     DATE,
    raw_description TEXT,
    fit_score       INTEGER,
    verdict         TEXT,
    reason          TEXT,
    scored_at       TIMESTAMPTZ,
    notified_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS jobs_unscored_idx
    ON jobs (created_at)
    WHERE fit_score IS NULL;

CREATE INDEX IF NOT EXISTS jobs_undigested_fit_idx
    ON jobs (scored_at DESC)
    WHERE verdict = 'fit' AND notified_at IS NULL;

CREATE INDEX IF NOT EXISTS jobs_source_posted_idx
    ON jobs (source, posted_date DESC);
