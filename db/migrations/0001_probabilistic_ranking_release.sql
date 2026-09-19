-- STEP-0017 migration 0001. Production derivative of the immutable STEP-0016 release.
-- No basketball fact, dimension, or ranking formula is defined here.

CREATE TABLE ranking_versions (
    release_id text PRIMARY KEY,
    release_fingerprint char(64) NOT NULL UNIQUE,
    generated_at_utc timestamptz NOT NULL,
    cutoff_season text NOT NULL,
    ranking_policy_version text NOT NULL,
    overall_substrate_version text NOT NULL,
    peak_version text NOT NULL,
    longevity_version text NOT NULL,
    defense_version text NOT NULL,
    player_count integer NOT NULL CHECK (player_count > 0),
    rankable_count integer NOT NULL CHECK (rankable_count >= 0),
    unavailable_count integer NOT NULL CHECK (unavailable_count >= 0),
    source_ranking_fingerprint char(64) NOT NULL,
    exact_overall_point_promoted boolean NOT NULL DEFAULT false,
    artifact_sha256 jsonb NOT NULL,
    upstream_sha256 jsonb NOT NULL,
    methodology_json jsonb NOT NULL,
    manifest_json jsonb NOT NULL,
    publication_rights_status text NOT NULL DEFAULT 'PUBLICATION_RIGHTS_REVIEW_REQUIRED',
    CHECK (player_count = rankable_count + unavailable_count),
    CHECK (NOT exact_overall_point_promoted),
    CHECK (publication_rights_status = 'PUBLICATION_RIGHTS_REVIEW_REQUIRED')
);

CREATE TABLE players (
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
CREATE INDEX players_search_name_idx ON players (release_id, search_name);
CREATE INDEX players_career_state_idx ON players (release_id, career_state);

CREATE TABLE player_rankings (
    release_id text NOT NULL,
    player_id text NOT NULL,
    display_position integer NOT NULL CHECK (display_position > 0),
    ranking_status text NOT NULL
        CHECK (ranking_status IN ('OFFICIAL', 'PROVISIONAL', 'INTERVAL_NATIVE')),
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
CREATE INDEX player_rankings_status_idx ON player_rankings (release_id, ranking_status);

CREATE TABLE player_rank_probabilities (
    release_id text NOT NULL,
    player_id text NOT NULL,
    top_1 double precision NOT NULL CHECK (top_1 BETWEEN 0 AND 1),
    top_5 double precision NOT NULL CHECK (top_5 BETWEEN 0 AND 1),
    top_10 double precision NOT NULL CHECK (top_10 BETWEEN 0 AND 1),
    top_25 double precision NOT NULL CHECK (top_25 BETWEEN 0 AND 1),
    top_50 double precision NOT NULL CHECK (top_50 BETWEEN 0 AND 1),
    top_100 double precision NOT NULL CHECK (top_100 BETWEEN 0 AND 1),
    top100_membership text NOT NULL,
    median_rank double precision NOT NULL,
    mean_rank double precision NOT NULL,
    rank_lower_50 double precision NOT NULL,
    rank_upper_50 double precision NOT NULL,
    rank_lower_80 double precision NOT NULL,
    rank_upper_80 double precision NOT NULL,
    rank_lower_90 double precision NOT NULL,
    rank_upper_90 double precision NOT NULL,
    rank_lower_95 double precision NOT NULL,
    rank_upper_95 double precision NOT NULL,
    PRIMARY KEY (release_id, player_id),
    FOREIGN KEY (release_id, player_id) REFERENCES player_rankings(release_id, player_id),
    CHECK (top_1 <= top_5 AND top_5 <= top_10 AND top_10 <= top_25
           AND top_25 <= top_50 AND top_50 <= top_100),
    CHECK (rank_lower_95 <= rank_lower_90 AND rank_lower_90 <= rank_lower_80
           AND rank_lower_80 <= rank_lower_50 AND rank_lower_50 <= median_rank
           AND median_rank <= rank_upper_50 AND rank_upper_50 <= rank_upper_80
           AND rank_upper_80 <= rank_upper_90 AND rank_upper_90 <= rank_upper_95)
);

CREATE TABLE player_dimensions (
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

-- Exact frozen STEP-0016 response payloads. Normalized tables remain the indexed/queryable
-- source for eligibility, filters, counts, and reconciliation; payloads preserve API equivalence.
CREATE TABLE player_profiles (
    release_id text NOT NULL,
    player_id text NOT NULL,
    profile_json jsonb NOT NULL,
    PRIMARY KEY (release_id, player_id),
    FOREIGN KEY (release_id, player_id) REFERENCES players(release_id, player_id)
);

CREATE TABLE top100_entries (
    release_id text NOT NULL,
    display_position integer NOT NULL CHECK (display_position BETWEEN 1 AND 100),
    player_id text NOT NULL,
    payload_json jsonb NOT NULL,
    PRIMARY KEY (release_id, display_position),
    UNIQUE (release_id, player_id),
    FOREIGN KEY (release_id, player_id) REFERENCES player_rankings(release_id, player_id)
);

CREATE FUNCTION reject_ranking_release_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'ranking release rows are immutable; create a new release_id';
END;
$$;

CREATE TRIGGER freeze_ranking_versions BEFORE UPDATE OR DELETE ON ranking_versions
    FOR EACH ROW EXECUTE FUNCTION reject_ranking_release_mutation();
CREATE TRIGGER freeze_players BEFORE UPDATE OR DELETE ON players
    FOR EACH ROW EXECUTE FUNCTION reject_ranking_release_mutation();
CREATE TRIGGER freeze_player_rankings BEFORE UPDATE OR DELETE ON player_rankings
    FOR EACH ROW EXECUTE FUNCTION reject_ranking_release_mutation();
CREATE TRIGGER freeze_player_rank_probabilities BEFORE UPDATE OR DELETE ON player_rank_probabilities
    FOR EACH ROW EXECUTE FUNCTION reject_ranking_release_mutation();
CREATE TRIGGER freeze_player_dimensions BEFORE UPDATE OR DELETE ON player_dimensions
    FOR EACH ROW EXECUTE FUNCTION reject_ranking_release_mutation();
CREATE TRIGGER freeze_player_profiles BEFORE UPDATE OR DELETE ON player_profiles
    FOR EACH ROW EXECUTE FUNCTION reject_ranking_release_mutation();
CREATE TRIGGER freeze_top100_entries BEFORE UPDATE OR DELETE ON top100_entries
    FOR EACH ROW EXECUTE FUNCTION reject_ranking_release_mutation();
