"""Coverage-aware diagnostic candidates for the eight proposed GOAT dimensions.

This module intentionally contains no overall score, player ranking, or final
dimension formula.  It provides deterministic primitives used to compare
candidate definitions in STEP-0012.
"""

from __future__ import annotations

import math
import random
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

DIMENSION_METHODOLOGY_VERSION = "goat-dimension-candidates-v1"
MONTE_CARLO_SEED = 120012
MONTE_CARLO_SAMPLES = 200
COVERAGE_THRESHOLD = 2.0 / 3.0

type Numeric = int | float


class Dimension(StrEnum):
    PEAK = "PEAK"
    LONGEVITY = "LONGEVITY"
    OFFENSE = "OFFENSE"
    DEFENSE = "DEFENSE"
    PLAYOFFS = "PLAYOFFS"
    ACCOLADES = "ACCOLADES"
    WINNING = "WINNING"
    ERA_DOMINANCE = "ERA_DOMINANCE"


class OwnershipType(StrEnum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    DIAGNOSTIC = "DIAGNOSTIC"
    EXCLUDED = "EXCLUDED"


class ScalingMethod(StrEnum):
    CAREER_UNIVERSE_PERCENTILE = "CAREER_UNIVERSE_PERCENTILE"
    ROBUST_STANDARDIZATION = "ROBUST_STANDARDIZATION"
    STANDARD_Z = "STANDARD_Z"
    EMPIRICAL_CDF = "EMPIRICAL_CDF"


class MissingnessPolicy(StrEnum):
    CORE_FEATURE_ONLY = "CORE_FEATURE_ONLY"
    AVAILABLE_FEATURE_RENORMALIZATION = "AVAILABLE_FEATURE_RENORMALIZATION"
    COVERAGE_THRESHOLD = "COVERAGE_THRESHOLD"
    ERA_SPECIFIC_ENRICHMENT = "ERA_SPECIFIC_ENRICHMENT"


class CoverageConfidence(StrEnum):
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    LIMITED = "LIMITED"
    UNAVAILABLE = "UNAVAILABLE"


class CandidateStatus(StrEnum):
    PROPOSED = "PROPOSED"
    VALIDATED_FOR_EXPERIMENT = "VALIDATED_FOR_EXPERIMENT"
    REJECTED = "REJECTED"
    DEFERRED = "DEFERRED"


@dataclass(frozen=True)
class PrimitiveSpec:
    name: str
    core: bool = True
    post_1996_only: bool = False
    source_methodology: str = "career-trajectory-peak-longevity-v1"


@dataclass(frozen=True)
class CandidateSpec:
    dimension: Dimension
    candidate_id: str
    name: str
    description: str
    primitives: tuple[PrimitiveSpec, ...]
    known_biases: tuple[str, ...] = ()
    status: CandidateStatus = CandidateStatus.PROPOSED


@dataclass(frozen=True)
class CombinedValue:
    value: float | None
    evidence_coverage_pct: float
    core_feature_coverage: float
    optional_feature_coverage: float | None
    confidence: CoverageConfidence
    components_used: int


def _finite(value: Numeric | None) -> float | None:
    if value is None:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def midranks(values: Sequence[float]) -> list[float]:
    """Return zero-based midranks, preserving ties."""
    ordered = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    ranks = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        rank = (index + end - 1) / 2.0
        for position in range(index, end):
            ranks[ordered[position][0]] = rank
        index = end
    return ranks


def scale_values(
    values: Mapping[str, Numeric | None],
    reference_players: set[str],
    method: ScalingMethod,
) -> dict[str, float | None]:
    """Scale one primitive against observed values in an explicit population."""
    observed = [
        (player_id, finite)
        for player_id, value in values.items()
        if player_id in reference_players and (finite := _finite(value)) is not None
    ]
    output: dict[str, float | None] = dict.fromkeys(values)
    if not observed:
        return output
    reference = [value for _, value in observed]
    ordered = sorted(reference)
    mean = statistics.fmean(reference)
    std = statistics.pstdev(reference)
    median = float(statistics.median(reference))
    deviations = [abs(value - median) for value in reference]
    mad = float(statistics.median(deviations))
    denominator = 1.4826 * mad

    def scale(value: float) -> float | None:
        if method is ScalingMethod.STANDARD_Z:
            return (value - mean) / std if std > 0.0 else None
        if method is ScalingMethod.ROBUST_STANDARDIZATION:
            return (value - median) / denominator if denominator > 0.0 else None
        less = sum(item < value for item in ordered)
        equal = sum(item == value for item in ordered)
        if method is ScalingMethod.CAREER_UNIVERSE_PERCENTILE:
            return (less + 0.5 * equal) / len(ordered)
        if method is ScalingMethod.EMPIRICAL_CDF:
            return (less + equal) / len(ordered)
        raise ValueError(f"unsupported scaling method: {method}")

    for player_id, value in values.items():
        finite = _finite(value)
        output[player_id] = scale(finite) if finite is not None else None
    return output


def coverage_confidence(available: int, expected: int) -> CoverageConfidence:
    if expected <= 0 or available <= 0:
        return CoverageConfidence.UNAVAILABLE
    ratio = available / expected
    if ratio == 1.0:
        return CoverageConfidence.STRONG
    if ratio >= 0.75:
        return CoverageConfidence.MODERATE
    return CoverageConfidence.LIMITED


def combine_components(
    values: Sequence[float | None],
    core_flags: Sequence[bool],
    policy: MissingnessPolicy,
    *,
    weights: Sequence[float] | None = None,
    coverage_threshold: float = COVERAGE_THRESHOLD,
) -> CombinedValue:
    if len(values) != len(core_flags):
        raise ValueError("values and core flags must have equal length")
    if weights is not None and len(weights) != len(values):
        raise ValueError("weights and values must have equal length")
    expected = len(values)
    available = sum(value is not None for value in values)
    core_expected = sum(core_flags)
    core_available = sum(
        value is not None for value, core in zip(values, core_flags, strict=True) if core
    )
    optional_expected = expected - core_expected
    optional_available = available - core_available
    coverage = available / expected if expected else 0.0
    core_coverage = core_available / core_expected if core_expected else 0.0
    optional_coverage = optional_available / optional_expected if optional_expected else None

    if policy is MissingnessPolicy.CORE_FEATURE_ONLY:
        indices = [index for index, core in enumerate(core_flags) if core]
        valid = bool(indices) and all(values[index] is not None for index in indices)
    elif policy is MissingnessPolicy.AVAILABLE_FEATURE_RENORMALIZATION:
        indices = [index for index, value in enumerate(values) if value is not None]
        valid = bool(indices)
    elif policy is MissingnessPolicy.COVERAGE_THRESHOLD:
        indices = [index for index, value in enumerate(values) if value is not None]
        valid = bool(indices) and coverage >= coverage_threshold
    elif policy is MissingnessPolicy.ERA_SPECIFIC_ENRICHMENT:
        indices = [
            index
            for index, (value, core) in enumerate(zip(values, core_flags, strict=True))
            if core and value is not None
        ]
        valid = bool(indices) and core_coverage >= coverage_threshold
    else:
        raise ValueError(f"unsupported missingness policy: {policy}")

    result: float | None = None
    if valid:
        selected_weights = [weights[index] if weights is not None else 1.0 for index in indices]
        total_weight = sum(selected_weights)
        if total_weight > 0.0:
            weighted_values: list[float] = []
            for position, index in enumerate(indices):
                component = values[index]
                if component is None:
                    raise AssertionError("selected component unexpectedly missing")
                weighted_values.append(float(component) * selected_weights[position])
            result = sum(weighted_values) / total_weight
    return CombinedValue(
        value=result,
        evidence_coverage_pct=coverage,
        core_feature_coverage=core_coverage,
        optional_feature_coverage=optional_coverage,
        confidence=coverage_confidence(available, expected),
        components_used=len(indices) if valid else 0,
    )


def pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = statistics.fmean(left)
    right_mean = statistics.fmean(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    left_ss = sum((x - left_mean) ** 2 for x in left)
    right_ss = sum((y - right_mean) ** 2 for y in right)
    denominator = math.sqrt(left_ss * right_ss)
    return numerator / denominator if denominator > 0.0 else None


def spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    return pearson(midranks(left), midranks(right))


def correlation_pair(
    left: Mapping[str, float | None], right: Mapping[str, float | None]
) -> dict[str, float | int | None]:
    shared = sorted(
        player_id
        for player_id in left.keys() & right.keys()
        if left[player_id] is not None and right[player_id] is not None
    )
    x = [float(left[player_id]) for player_id in shared]  # type: ignore[arg-type]
    y = [float(right[player_id]) for player_id in shared]  # type: ignore[arg-type]
    return {"n": len(shared), "pearson": pearson(x, y), "spearman": spearman(x, y)}


def simplex_weights(component_count: int, samples: int, seed: int) -> list[tuple[float, ...]]:
    """Deterministic uniform-simplex weights via normalized exponential draws."""
    if component_count <= 0 or samples <= 0:
        raise ValueError("component_count and samples must be positive")
    generator = random.Random(seed)
    output: list[tuple[float, ...]] = []
    for _ in range(samples):
        draws = [-math.log(max(generator.random(), 1e-15)) for _ in range(component_count)]
        total = sum(draws)
        output.append(tuple(value / total for value in draws))
    return output


def ordering_stability(
    baseline: Mapping[str, float],
    simulations: Sequence[Mapping[str, float]],
    *,
    pair_limit: int = 250,
    seed: int = MONTE_CARLO_SEED,
) -> float | None:
    players = sorted(baseline)
    pairs = [(left, right) for index, left in enumerate(players) for right in players[index + 1 :]]
    if not pairs or not simulations:
        return None
    generator = random.Random(seed)
    selected = generator.sample(pairs, min(pair_limit, len(pairs)))
    agreement = 0
    comparisons = 0
    for simulation in simulations:
        for left, right in selected:
            if left not in simulation or right not in simulation:
                continue
            baseline_order = (baseline[left] > baseline[right]) - (baseline[left] < baseline[right])
            simulated_order = (simulation[left] > simulation[right]) - (
                simulation[left] < simulation[right]
            )
            agreement += baseline_order == simulated_order
            comparisons += 1
    return agreement / comparisons if comparisons else None


def era_group(first_season: int | None) -> str:
    if first_season is None:
        return "UNKNOWN"
    if first_season < 1960:
        return "PRE_1960"
    if first_season < 1970:
        return "1960S"
    if first_season < 1980:
        return "1970S"
    if first_season < 1990:
        return "1980S"
    if first_season < 2000:
        return "1990S"
    if first_season < 2010:
        return "2000S"
    if first_season < 2020:
        return "2010S"
    return "2020S"


def shared_primitive_lineage(left: CandidateSpec, right: CandidateSpec) -> tuple[str, ...]:
    return tuple(
        sorted({item.name for item in left.primitives} & {item.name for item in right.primitives})
    )


def rejection_reasons(
    *,
    available_rate: float,
    post_1996_dependency: bool,
    ordering_stability_value: float | None,
    redundant_correlation: float | None,
    shared_lineage_count: int,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if available_rate < 0.50:
        reasons.append("SEVERE_COVERAGE_LIMITATION")
    if post_1996_dependency:
        reasons.append("HIDDEN_MODERN_ERA_DEPENDENCY")
    if ordering_stability_value is not None and ordering_stability_value < 0.75:
        reasons.append("WEIGHT_SENSITIVE")
    if (
        redundant_correlation is not None
        and abs(redundant_correlation) >= 0.98
        and shared_lineage_count > 0
    ):
        reasons.append("NEAR_DUPLICATE_SIGNAL")
    return tuple(reasons)


def _p(
    name: str,
    *,
    core: bool = True,
    modern: bool = False,
    source: str = "career-trajectory-peak-longevity-v1",
) -> PrimitiveSpec:
    return PrimitiveSpec(name, core, modern, source)


def candidate_specs() -> tuple[CandidateSpec, ...]:
    """Return the frozen STEP-0012 candidate catalog (none are FINAL)."""
    awards = "official-player-awards-canonical-v1+all-star-stat-leader-facts-v1"
    team = "team-success-postseason-v1"
    return (
        CandidateSpec(
            Dimension.PEAK,
            "PEAK-A",
            "Single-season dominance",
            "Best qualified season across cross-era performance primitives.",
            tuple(_p(f"reg_{m}_peak1_quality") for m in ("ppg", "rpg", "apg", "ts_pct")),
        ),
        CandidateSpec(
            Dimension.PEAK,
            "PEAK-B",
            "Three-year contiguous prime",
            "Best complete contiguous three-season quality window.",
            tuple(_p(f"reg_{m}_peak3_quality") for m in ("ppg", "rpg", "apg", "ts_pct")),
        ),
        CandidateSpec(
            Dimension.PEAK,
            "PEAK-C",
            "Five-year contiguous prime",
            "Best complete contiguous five-season quality window.",
            tuple(_p(f"reg_{m}_peak5_quality") for m in ("ppg", "rpg", "apg", "ts_pct")),
        ),
        CandidateSpec(
            Dimension.PEAK,
            "PEAK-D",
            "Multi-horizon peak",
            "Parallel one-, three-, and five-season evidence without a final horizon choice.",
            tuple(_p(f"reg_{m}_peak{w}_quality") for w in (1, 3, 5) for m in ("ppg", "rpg", "apg")),
            ("Correlated horizons can duplicate one performance signal.",),
        ),
        CandidateSpec(
            Dimension.PEAK,
            "PEAK-E",
            "Availability-aware peak",
            "Opportunity-adjusted three-season peak kept separate from quality peak.",
            tuple(_p(f"reg_{m}_peak3_adjusted") for m in ("ppg", "rpg", "apg", "ts_pct")),
        ),
        CandidateSpec(
            Dimension.LONGEVITY,
            "LONGEVITY-A",
            "Elite-season count",
            "Counts at multiple percentile thresholds across core categories.",
            tuple(
                _p(f"reg_{m}_elite_{t}")
                for m in ("ppg", "rpg", "apg")
                for t in ("p80", "p90", "p95")
            ),
        ),
        CandidateSpec(
            Dimension.LONGEVITY,
            "LONGEVITY-B",
            "Cumulative dominance",
            "Cumulative positive z and percentile area above elite baselines.",
            tuple(
                _p(f"reg_{m}_{kind}")
                for m in ("ppg", "rpg", "apg", "ts_pct")
                for kind in ("cum_positive_z", "area_p80")
            ),
        ),
        CandidateSpec(
            Dimension.LONGEVITY,
            "LONGEVITY-C",
            "Prime persistence",
            "Longest repeated elite runs at several thresholds.",
            tuple(
                _p(f"reg_{m}_run_{t}") for m in ("ppg", "rpg", "apg") for t in ("p80", "p90", "p95")
            ),
        ),
        CandidateSpec(
            Dimension.LONGEVITY,
            "LONGEVITY-D",
            "Participation plus quality",
            "Qualified seasons and games alongside average era-relative quality.",
            (
                _p("regular_qualified_seasons"),
                _p("regular_total_games"),
                _p("reg_ppg_mean_z"),
                _p("reg_apg_mean_z"),
                _p("reg_rpg_mean_z"),
            ),
        ),
        CandidateSpec(
            Dimension.LONGEVITY,
            "LONGEVITY-E",
            "High-bar longevity",
            "Seasons remaining at the 90th and 95th percentiles.",
            tuple(
                _p(f"reg_{m}_elite_{t}")
                for m in ("ppg", "rpg", "apg", "ts_pct")
                for t in ("p90", "p95")
            ),
        ),
        CandidateSpec(
            Dimension.OFFENSE,
            "OFFENSE-A",
            "Cross-era core",
            "Broad scoring and playmaking with efficiency when supported.",
            (_p("reg_ppg_mean_z"), _p("reg_apg_mean_z"), _p("reg_ts_pct_mean_z", core=False)),
        ),
        CandidateSpec(
            Dimension.OFFENSE,
            "OFFENSE-B",
            "Balanced scoring plus playmaking",
            "Scoring and creation kept as equal, separately scaled evidence.",
            (_p("reg_ppg_mean_z"), _p("reg_apg_mean_z")),
        ),
        CandidateSpec(
            Dimension.OFFENSE,
            "OFFENSE-C",
            "Efficiency-adjusted production",
            "Scoring volume with TS and eFG efficiency evidence.",
            (_p("reg_ppg_mean_z"), _p("reg_ts_pct_mean_z"), _p("reg_efg_pct_mean_z", core=False)),
        ),
        CandidateSpec(
            Dimension.OFFENSE,
            "OFFENSE-D",
            "Modern enriched offense",
            "Post-1996 possession-rate scoring plus playmaking and efficiency.",
            (
                _p("reg_points_per_75_mean_z", modern=True),
                _p("modern_reg_apg_mean_z", modern=True),
                _p("modern_reg_ts_pct_mean_z", modern=True),
            ),
            ("Not universally comparable before 1996-97.",),
        ),
        CandidateSpec(
            Dimension.DEFENSE,
            "DEFENSE-A",
            "Box-performance core",
            "Individual rebounding, steals, and blocks only where recorded.",
            (
                _p("reg_rpg_mean_z"),
                _p("reg_spg_mean_z", core=False),
                _p("reg_bpg_mean_z", core=False),
            ),
            ("Steals and blocks do not exist before 1973-74.",),
        ),
        CandidateSpec(
            Dimension.DEFENSE,
            "DEFENSE-B",
            "Honors augmented",
            "Box evidence plus factual DPOY and All-Defense evidence.",
            (
                _p("reg_rpg_mean_z"),
                _p("reg_spg_mean_z", core=False),
                _p("reg_bpg_mean_z", core=False),
                _p("dpoy_count", core=False, source=awards),
                _p("all_defense_total_count", core=False, source=awards),
            ),
            ("Defensive honors overlap ACCOLADES and begin well after league founding.",),
        ),
        CandidateSpec(
            Dimension.DEFENSE,
            "DEFENSE-C",
            "Modern advanced defense",
            "Post-1996 season-relative defensive-rating evidence.",
            (
                _p(
                    "modern_def_rating_mean_z",
                    modern=True,
                    source="GOATLAB-HIST-V1:player_season_advanced",
                ),
                _p("modern_reg_spg_mean_z", modern=True),
                _p("modern_reg_bpg_mean_z", modern=True),
            ),
            ("Official advanced coverage begins in 1996-97.",),
        ),
        CandidateSpec(
            Dimension.DEFENSE,
            "DEFENSE-D",
            "Coverage-bridged defense",
            "Rebounding core with honors as explicit historical bridge evidence.",
            (
                _p("reg_rpg_mean_z"),
                _p("dpoy_count", core=False, source=awards),
                _p("all_defense_total_count", core=False, source=awards),
            ),
            ("Bridge is incomplete before All-Defense and DPOY introductions.",),
        ),
        CandidateSpec(
            Dimension.PLAYOFFS,
            "PLAYOFFS-A",
            "Absolute postseason performance",
            "Career mean playoff scoring, rebounding, creation, and efficiency.",
            tuple(_p(f"po_{m}_mean_z") for m in ("ppg", "rpg", "apg", "ts_pct")),
        ),
        CandidateSpec(
            Dimension.PLAYOFFS,
            "PLAYOFFS-B",
            "Postseason peak",
            "Best playoff season and best complete three-season playoff windows.",
            tuple(_p(f"po_{m}_peak{w}_quality") for m in ("ppg", "rpg", "apg") for w in (1, 3)),
        ),
        CandidateSpec(
            Dimension.PLAYOFFS,
            "PLAYOFFS-C",
            "Postseason longevity",
            "Playoff seasons, games, and cumulative dominance.",
            (
                _p("playoff_seasons"),
                _p("playoff_games"),
                _p("po_ppg_cum_positive_z"),
                _p("po_apg_cum_positive_z"),
                _p("po_rpg_cum_positive_z"),
            ),
        ),
        CandidateSpec(
            Dimension.PLAYOFFS,
            "PLAYOFFS-D",
            "Regular-to-playoff change",
            "Difference between playoff and regular-season normalized performance; no ratios.",
            tuple(_p(f"{m}_playoff_lift") for m in ("ppg", "rpg", "apg", "ts_pct")),
            ("Selection into playoffs and small samples affect interpretation.",),
        ),
        CandidateSpec(
            Dimension.PLAYOFFS,
            "PLAYOFFS-E",
            "Sample-aware postseason impact",
            "Opportunity-weighted playoff cumulative production with sample metadata.",
            (
                *(_p(f"po_{m}_weighted_positive_z") for m in ("ppg", "rpg", "apg")),
                _p("playoff_games"),
            ),
        ),
        CandidateSpec(
            Dimension.ACCOLADES,
            "ACCOLADES-A",
            "Raw major-award profile",
            "Separately scaled factual major-award counts.",
            tuple(
                _p(name, source=awards)
                for name in (
                    "mvp_count",
                    "finals_mvp_count",
                    "dpoy_count",
                    "all_nba_total_count",
                    "all_defense_total_count",
                )
            ),
            ("PlayerAwards was candidate-scoped; NOT_QUERIED remains missing.",),
        ),
        CandidateSpec(
            Dimension.ACCOLADES,
            "ACCOLADES-B",
            "Award-scarcity normalized",
            "Observed events weighted only by empirical event scarcity, not manual points.",
            (_p("award_scarcity_index", source=awards),),
        ),
        CandidateSpec(
            Dimension.ACCOLADES,
            "ACCOLADES-C",
            "Award-opportunity normalized",
            "Major events divided by applicable career-season opportunity.",
            (_p("award_opportunity_index", source=awards),),
            ("Opportunity does not encode voting strength or award slots beyond applicability.",),
        ),
        CandidateSpec(
            Dimension.ACCOLADES,
            "ACCOLADES-D",
            "Honor-level persistence",
            "Persistent All-NBA, All-Defense, All-Star roster, and title evidence.",
            (
                _p("all_nba_total_count", source=awards),
                _p("all_defense_total_count", source=awards),
                _p("all_star_roster_seasons", source="all-star-stat-leader-facts-v1"),
                _p("stat_title_count", source="all-star-stat-leader-facts-v1"),
            ),
        ),
        CandidateSpec(
            Dimension.ACCOLADES,
            "ACCOLADES-E",
            "Major-winner emphasis",
            "MVP, Finals MVP, and DPOY winner-event profile without equivalence weights.",
            tuple(
                _p(name, source=awards) for name in ("mvp_count", "finals_mvp_count", "dpoy_count")
            ),
        ),
        CandidateSpec(
            Dimension.WINNING,
            "WINNING-A",
            "Team outcomes",
            "Team strength, playoffs, Finals, and regular champion-team membership.",
            tuple(
                _p(name, source=team)
                for name in (
                    "mean_team_win_percentile",
                    "playoff_seasons",
                    "finals_seasons",
                    "champion_regular_seasons",
                )
            ),
        ),
        CandidateSpec(
            Dimension.WINNING,
            "WINNING-B",
            "Participation-qualified winning",
            "Postseason participation and championships with actual playoff participation.",
            tuple(
                _p(name, source=team)
                for name in ("playoff_games", "playoff_wins", "champion_playoff_seasons")
            ),
        ),
        CandidateSpec(
            Dimension.WINNING,
            "WINNING-C",
            "Finals-participation winning",
            "Finals games and championships with actual Finals participation.",
            tuple(
                _p(name, source=team)
                for name in ("finals_seasons", "finals_games", "champion_finals_seasons")
            ),
        ),
        CandidateSpec(
            Dimension.WINNING,
            "WINNING-D",
            "Role/opportunity-aware winning",
            "Game-share proxies and outcome facts without a subjective role label.",
            (
                _p("mean_regular_game_share", source=team),
                _p("mean_playoff_game_share", core=False, source=team),
                _p("mean_finals_game_share", core=False, source=team),
                _p("champion_finals_seasons", core=False, source=team),
            ),
        ),
        CandidateSpec(
            Dimension.WINNING,
            "WINNING-E",
            "Sustained team success",
            "Repeated elite-team, playoff, Finals, and participant-champion seasons.",
            tuple(
                _p(name, source=team)
                for name in (
                    "elite_team_seasons",
                    "playoff_seasons",
                    "finals_seasons",
                    "champion_playoff_seasons",
                )
            ),
        ),
        CandidateSpec(
            Dimension.ERA_DOMINANCE,
            "ERA-A",
            "Single-season extremeness",
            "Maximum single-season z-score across core statistical categories.",
            tuple(_p(f"reg_{m}_max_z") for m in ("ppg", "rpg", "apg")),
        ),
        CandidateSpec(
            Dimension.ERA_DOMINANCE,
            "ERA-B",
            "Multi-season era dominance",
            "Best three-season mean across core statistical categories.",
            tuple(_p(f"reg_{m}_top3_z") for m in ("ppg", "rpg", "apg")),
        ),
        CandidateSpec(
            Dimension.ERA_DOMINANCE,
            "ERA-C",
            "Category-breadth dominance",
            "Number of core categories with 90th-percentile seasons.",
            tuple(_p(f"reg_{m}_elite_p90") for m in ("ppg", "rpg", "apg", "ts_pct")),
        ),
        CandidateSpec(
            Dimension.ERA_DOMINANCE,
            "ERA-D",
            "Percentile separation",
            "Area above the 90th-percentile baseline across core categories.",
            tuple(_p(f"reg_{m}_area_p90") for m in ("ppg", "rpg", "apg", "ts_pct")),
        ),
        CandidateSpec(
            Dimension.ERA_DOMINANCE,
            "ERA-E",
            "Career era dominance",
            "Cumulative positive season z-scores across core categories.",
            tuple(_p(f"reg_{m}_cum_positive_z") for m in ("ppg", "rpg", "apg", "ts_pct")),
        ),
    )
