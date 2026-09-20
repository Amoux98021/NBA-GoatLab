# Frontend component and disclosure map

| Surface | Source | Presentation rule |
|---|---|---|
| Home `/` | `/api/v1/top100` | Exactly 100 API-ordered navigation slots; no client sort. Nearby cutoff preview comes from the paginated API and is not the complete bubble artifact. |
| Full `/leaderboard` | `/api/v1/leaderboard` | GET-form search, active/status filters, and offset pagination are backend-owned; API display order is retained. |
| `/players/[playerId]` | `/api/v1/players/{id}` | Canonical ID route; seven dimensions, Overall/rank distributions, Top-1/5/10/25/50/100, and evidence status. Unavailable careers retain identity and factual dimension evidence. |
| `/methodology` | `/api/v1/methodology` and `/releases/{id}` | Frozen versions, cutoff, rank interpretation, historical limits, status semantics, and display-only seven weights. |

`LeaderboardTable` presents a semantic desktop table and keyboard-linked mobile/tablet cards.
`StatusBadge` is neutral; it does not encode quality. `Probability` uses an exact textual
percentage alongside its optional decorative bar; nonzero probabilities near 100% are never
rounded into false certainty. `DimensionCard` renders interval-only scores as 90% ranges and
missing values as “Insufficient evidence”, never `0`. `UncertaintyInfo` and keyboard/touch
`InfoTip` provide progressive disclosure. Loading skeletons, not-found content, and a generic
API error boundary avoid raw trace disclosure.

The only Client Component is the Next.js error boundary. All ranking pages fetch on the
server. `NEXT_PUBLIC_API_BASE_URL` is centralized in the typed client and absent from visual
components. Immutable responses use one-hour Next.js fetch revalidation; the configured
release ID is checked on every response. Player links disable bulk prefetch so scrolling a
100-row page does not request many profiles. No frontend code computes dimension scores,
probabilities, rank order, or pairwise comparisons.

At widths up to 760 px, cards stack vertically. At 761–900 px, they form two columns.
At 1024 px the semantic table may scroll horizontally *inside its labeled keyboard-focusable
region*; the page itself does not overflow. At 1440 px it fits without inner scrolling.
