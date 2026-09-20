# Frontend component and disclosure map

| Surface | Source | Presentation rule |
|---|---|---|
| Home `/` | `/api/v1/top100` | Exactly 100 API-ordered navigation slots; no client sort. Nearby cutoff preview comes from the paginated API and is not the complete bubble artifact. |
| Full `/leaderboard` | `/api/v1/leaderboard` | GET-form search, active/status filters, and offset pagination are backend-owned; API display order is retained. |
| `/players/[playerId]` | `/api/v1/players/{id}` | Canonical ID route; seven dimensions, Overall/rank distributions, Top-1/5/10/25/50/100, and evidence status. Unavailable careers retain identity and factual dimension evidence. |
| `/methodology` | `/api/v1/methodology` and `/releases/{id}` | Frozen versions, cutoff, rank interpretation, historical limits, status semantics, and display-only seven weights. |
| `/compare` | `/api/v1/leaderboard` via same-origin search proxy | Canonical-ID selector with keyboard search, duplicate prevention, swap, and profile preselection; search covers distribution-rankable careers. |
| `/compare/[playerA]/[playerB]` | `/api/v1/compare/{A}/{B}` and two `/players/{id}` profiles | Shareable URL, backend-owned paired-draw probability/order label, seven dimension statuses, rank and Overall ranges, and explicit unavailable/same/unknown/service-error states. |

`LeaderboardTable` presents a semantic desktop table and keyboard-linked mobile/tablet cards.
`StatusBadge` is neutral; it does not encode quality. `Probability` uses an exact textual
percentage alongside its optional decorative bar; nonzero probabilities near 100% are never
rounded into false certainty. `DimensionCard` renders interval-only scores as 90% ranges and
missing values as “Insufficient evidence”, never `0`. `UncertaintyInfo` and keyboard/touch
`InfoTip` provide progressive disclosure. Loading skeletons, not-found content, and a generic
API error boundary avoid raw trace disclosure.

Comparison adds small Client Components for player selection and copy-link feedback alongside
the Next.js error boundary. Result data still fetch server-side; no browser code evaluates
paired draws, rank probabilities, dimension formulas, or ordering thresholds. The selector's
same-origin search route projects only canonical identities and statuses from the frozen
backend response. `NEXT_PUBLIC_API_BASE_URL` is centralized in the typed client and absent from visual
components. Immutable responses use one-hour Next.js fetch revalidation; the configured
release ID is checked on every response. Player links disable bulk prefetch so scrolling a
100-row page does not request many profiles. No frontend code computes dimension scores,
probabilities, rank order, or pairwise comparisons.

At widths up to 760 px, cards stack vertically. At 761–900 px, they form two columns.
At 1024 px the semantic table may scroll horizontally *inside its labeled keyboard-focusable
region*; the page itself does not overflow. At 1440 px it fits without inner scrolling. The
comparison hero stacks A/probability/B on mobile. Its semantic dimension table preserves
visible player labels in narrow layouts. Interval-native dimensions display ranges, never
standalone centers. Interpretation lists factual point summaries only where both exist; it
does not invent numerical dimension contributions or causal probability attribution.
