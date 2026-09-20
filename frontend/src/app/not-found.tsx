import Link from "next/link";

export default function NotFound() {
  return <div className="shell empty-state interior-page" role="status">
    <p className="eyebrow">PLAYER NOT FOUND</p>
    <h1>We couldn’t find that profile.</h1>
    <p>Check the player link or return to the leaderboard. No substitute player record is shown.</p>
    <Link className="button button--dark" href="/leaderboard">Explore the leaderboard</Link>
  </div>;
}
