"use client";

import Link from "next/link";

export default function ComparisonError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <div className="shell interior-page empty-state" role="alert"><p className="eyebrow">COMPARISON UNAVAILABLE</p><h1>We couldn’t load this matchup.</h1><p>The ranking service may be temporarily unavailable. GOATLab will not substitute a probability or midpoint.</p><div className="error-actions"><button className="button button--dark" onClick={reset}>Try again</button><Link className="button button--outline" href="/compare">Choose players</Link></div></div>;
}
