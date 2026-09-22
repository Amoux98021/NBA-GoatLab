import type { ReactNode } from "react";
import type { DimensionProfile, RankingStatus } from "@/lib/types";
import { dimensionDisplay, number, percent, rank, statusLabel } from "@/lib/display";

export function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  return <details className="info-tip"><summary aria-label={`About ${label}`} title={`About ${label}`}>i</summary><div className="info-tip__content" role="note">{children}</div></details>;
}

export function StatusBadge({ status }: { status: RankingStatus | string }) {
  return <span className="status-badge">{statusLabel(status)}</span>;
}

export function RankBand({ median, lower, upper, level = 80 }: { median: number; lower: number; upper: number; level?: number }) {
  return <span className="rank-band"><strong>{rank(median)}</strong><span className="rank-band__range">{level}% band {rank(lower)}–{rank(upper)}</span></span>;
}

export function Probability({ label, value, bar = false }: { label: string; value: number; bar?: boolean }) {
  return <div className={bar ? "probability probability--bar" : "probability"} aria-label={`${label} probability ${percent(value)}`}>
    <span>{label}</span><strong>{percent(value)}</strong>
    {bar && <div className="probability__track" data-probability-bar aria-hidden="true"><span className="probability__fill" style={{ width: `${value * 100}%` }} /></div>}
  </div>;
}

export function OverallRange({ lower, upper, center, status }: { lower: number; upper: number; center: number | null; status: RankingStatus }) {
  return <div className="overall-range"><strong>{number(lower)}–{number(upper)}</strong><span>Overall · 90% range</span>{center !== null && status !== "INTERVAL_NATIVE" && <small>Summary estimate {number(center)}</small>}</div>;
}

export function DimensionCard({ value, description }: { value: DimensionProfile; description: string }) {
  const unavailable = value.point_value === null && value.lower_90 === null && value.upper_90 === null;
  const interval = value.status.includes("INTERVAL_ONLY");
  return <article className="dimension-card" data-reveal>
    <div className="dimension-card__top"><h3>{value.dimension.charAt(0) + value.dimension.slice(1).toLowerCase()}</h3><StatusBadge status={value.status} /></div>
    <p className="dimension-card__value">{dimensionDisplay(value)}{!unavailable && <span> / 100</span>}</p>
    {interval && <p className="dimension-card__note">90% range · no exact point claim</p>}
    <p className="dimension-card__description">{description}</p>
    {value.dimension === "PEAK" && typeof value.evidence_metadata.best_supported_window === "string" && <p className="dimension-card__foot">Best-supported window: {value.evidence_metadata.best_supported_window.replaceAll("-", "–")}</p>}
  </article>;
}

export function UncertaintyInfo({ compact = false }: { compact?: boolean }) {
  return <aside className={compact ? "uncertainty-note uncertainty-note--compact" : "uncertainty-note"} data-reveal>
    <span className="uncertainty-note__icon" aria-hidden="true">◌</span>
    <div><strong>How to read this list</strong><p>GOATLab estimates both performance and how precisely historical evidence lets us measure it. A display position summarizes a rank distribution; nearby players may not be definitively ordered. Wider uncertainty does not mean lower player quality.</p></div>
  </aside>;
}
