export default function Loading() {
  return <div className="shell interior-page" aria-busy="true" aria-label="Loading leaderboard"><div className="skeleton skeleton--title" /><div className="skeleton skeleton--intro" /><div className="skeleton-list">{Array.from({ length: 8 }, (_, index) => <div key={index} className="skeleton skeleton--row" />)}</div></div>;
}
