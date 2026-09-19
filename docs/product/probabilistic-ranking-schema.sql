-- STEP-0016: release-scoped derived analytics, not raw source records.
-- Bulk loads use data/product/<release_id>/db/*.parquet via a transactional loader.
-- A previously published release is append-only; create a new release_id for changes.

CREATE TABLE IF NOT EXISTS ranking_versions (
    release_id text PRIMARY KEY,
    generated_at_utc timestamptz NOT NULL,
    cutoff_season text NOT NULL,
    ranking_policy_version text NOT NULL,
    overall_substrate_version text NOT NULL,
    source_ranking_fingerprint char(64) NOT NULL,
    exact_overall_point_promoted boolean NOT NULL DEFAULT false,
    CHECK (NOT exact_overall_point_promoted)
);

CREATE TABLE IF NOT EXISTS players (
    release_id text NOT NULL REFERENCES ranking_versions(release_id),
    player_id text NOT NULL,
    player_name text NOT NULL,
    search_name text NOT NULL,
    career_state text NOT NULL CHECK (career_state IN ('ACTIVE', 'RETIRED', 'UNKNOWN')),
    career_start_season integer,
    career_end_season integer,
    latest_season_used integer,
    PRIMARY KEY (release_id, player_id),
    CHECK (career_state <> 'ACTIVE' OR career_end_season IS NULL)
);
CREATE INDEX IF NOT EXISTS players_search_name_idx ON players (release_id, search_name);

CREATE TABLE IF NOT EXISTS player_rankings (
    release_id text NOT NULL,
    player_id text NOT NULL,
    display_position integer NOT NULL CHECK (display_position > 0),
    ranking_status text NOT NULL CHECK (ranking_status IN ('OFFICIAL', 'PROVISIONAL', 'INTERVAL_NATIVE')),
    overall_source_status text NOT NULL,
    overall_center double precision,
    overall_json jsonb NOT NULL,
    rank_json jsonb NOT NULL,
    distribution_ref text NOT NULL,
    distribution_fingerprint char(64) NOT NULL,
    PRIMARY KEY (release_id, player_id),
    UNIQUE (release_id, display_position),
    FOREIGN KEY (release_id, player_id) REFERENCES players(release_id, player_id)
);

CREATE TABLE IF NOT EXISTS player_rank_probabilities (
    release_id text NOT NULL,
    player_id text NOT NULL,
    top_1 double precision NOT NULL CHECK (top_1 BETWEEN 0 AND 1),
    top_5 double precision NOT NULL CHECK (top_5 BETWEEN 0 AND 1),
    top_10 double precision NOT NULL CHECK (top_10 BETWEEN 0 AND 1),
    top_25 double precision NOT NULL CHECK (top_25 BETWEEN 0 AND 1),
    top_50 double precision NOT NULL CHECK (top_50 BETWEEN 0 AND 1),
    top_100 double precision NOT NULL CHECK (top_100 BETWEEN 0 AND 1),
    top100_membership text NOT NULL,
    PRIMARY KEY (release_id, player_id),
    FOREIGN KEY (release_id, player_id) REFERENCES player_rankings(release_id, player_id),
    CHECK (top_1 <= top_5 AND top_5 <= top_10 AND top_10 <= top_25
           AND top_25 <= top_50 AND top_50 <= top_100)
);

CREATE TABLE IF NOT EXISTS player_dimensions (
    release_id text NOT NULL,
    player_id text NOT NULL,
    dimension text NOT NULL CHECK (dimension IN (
        'PEAK', 'LONGEVITY', 'OFFENSE', 'DEFENSE', 'PLAYOFFS', 'ACCOLADES', 'WINNING'
    )),
    status text NOT NULL,
    point_value double precision CHECK (point_value BETWEEN 0 AND 100),
    diagnostic_center double precision CHECK (diagnostic_center BETWEEN 0 AND 100),
    lower_90 double precision CHECK (lower_90 BETWEEN 0 AND 100),
    upper_90 double precision CHECK (upper_90 BETWEEN 0 AND 100),
    methodology_version text NOT NULL,
    confidence text,
    reason_codes_json jsonb NOT NULL,
    evidence_metadata_json jsonb NOT NULL,
    PRIMARY KEY (release_id, player_id, dimension),
    FOREIGN KEY (release_id, player_id) REFERENCES players(release_id, player_id),
    CHECK (lower_90 IS NULL OR upper_90 IS NULL OR lower_90 <= upper_90),
    CHECK (status NOT LIKE '%INTERVAL_ONLY%' OR point_value IS NULL)
);

-- Transactional importer must load: ranking_versions, players, player_rankings,
-- player_rank_probabilities, player_dimensions; verify release manifest hashes first.
-- No UPDATE/DELETE path is part of the public loader. A database role for published
-- analytics should have SELECT/INSERT only; a new release_id is required for revision.
