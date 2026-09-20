import Link from "next/link";
export default function PlayerNotFound() {
  return <div className="shell empty-state interior-page"><p className="eyebrow">PLAYER NOT FOUND</p><h1>That profile isn’t in this release.</h1><p>Check the player ID or return to the leaderboard.</p><Link className="button button--dark" href="/leaderboard">Browse players</Link></div>;
}
