import Link from "next/link";

export default function ComparisonNotFound() {
  return <div className="shell interior-page empty-state"><p className="eyebrow">PLAYER NOT FOUND</p><h1>That matchup is not in this release.</h1><p>One of the canonical player IDs could not be found. No substitute comparison is shown.</p><Link className="button button--dark" href="/compare">Choose players</Link></div>;
}
