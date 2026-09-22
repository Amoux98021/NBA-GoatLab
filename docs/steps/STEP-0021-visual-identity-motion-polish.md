# STEP-0021 — Visual identity and motion polish

Date: 2026-09-22  
Status: PASS  
Scope: presentation only

## Objective

Refine the structurally successful deployed frontend toward a visual identity of basketball court,
research lab, and editorial data product. The existing information architecture, routes,
server-rendered data ownership, API contracts, frozen release, and probabilistic semantics remain
unchanged.

## Visual identity

The frontend now uses the approved palette:

- graphite/midnight `#15171A` for the editorial/research foundation;
- warm paper `#F4F1E9` for the reading surface;
- hardwood amber `#C8793A` for basketball identity and primary actions;
- muted court tan `#D8C3A5` for boundaries and supporting surfaces;
- probability blue `#6F9FBE` for uncertainty, intervals, ranges, and probabilities;
- slate `#68727A` for secondary information;
- white `#FFFFFF` for clear content surfaces.

The home hero gains a restrained half-court/wood analytical texture composed entirely in local CSS.
Cards remain flat, borders remain structural, and shadows/gradients are deliberately limited. No
team marks, NBA-logo imitation, player photography, or third-party visual service was introduced.

## Language correction

The frontend now distinguishes the two production populations:

- 5,103 canonical player profiles;
- 1,882 careers with calibrated joint Overall/rank distributions.

“Explore all 1,882 players” was replaced with “Explore full leaderboard.” Leaderboard result copy
now says “rankable careers,” and the home/leaderboard introductions state the relationship between
the rankable population and complete profile population. The 3,221 unavailable careers are not
silently inserted into the leaderboard.

## Motion system

A small local `MotionEnhancer` Client Component uses one IntersectionObserver for reusable,
once-only viewport reveals. Server Components and server fetching remain the default.

- hero eyebrow, headline, and actions reveal over less than 800 ms;
- the word “modeled.” receives a restrained probability-blue line reveal;
- content moves approximately 12 px with opacity on first viewport entry;
- leaderboard rows use only hover/focus surface transitions and arrows move 4 px;
- provided probability bars and comparison splits animate to their existing exact values;
- no row staggering, number roulette, probability recomputation, or animation-time data request;
- without JavaScript, all content and exact bar values remain visible;
- `prefers-reduced-motion` disables meaningful motion and animated texture movement.

## Runtime and API impact

- no new dependency;
- no third-party JavaScript or image service;
- no polling, keepalive, scroll fetching, per-card request, or automatic refresh;
- no change to Next.js server rendering, API request shape, fetch revalidation, or profile-link
  prefetch suppression;
- the observer operates only on DOM already present in the response.

Expected backend request impact: **zero additional requests**.

## Accessibility

- keyboard focus remains explicit and now uses the amber identity color;
- semantic table, heading, navigation, and disclosure structures remain intact;
- exact percentages remain textual rather than being communicated only through animation/color;
- no content depends on motion to become usable;
- reduced-motion users receive an immediate static experience;
- desktop, tablet, and mobile breakpoints preserve the existing responsive structure.

## Verification

- frontend ESLint;
- TypeScript no-emit check;
- frontend component/API tests, including exact probability-value preservation in animated markup;
- Next.js production build;
- responsive and reduced-motion source/behavior review;
- request-path diff review confirming no new fetches or remote dependencies;
- repository diff and frozen-methodology review.

## Methodology preservation

No basketball formula, weight, trained model, player score, probability distribution, frozen
release artifact, calibration gate, status semantic, or ranking policy changed. STEP-0021 is a
presentation-only successor to the deployed frontend.
