import type { Metadata } from "next";
import Link from "next/link";
import { getLeaderboard } from "@/lib/api";
import type { LeaderboardQuery } from "@/lib/api";
import { LeaderboardTable } from "@/components/leaderboard";
import { UncertaintyInfo } from "@/components/primitives";

export const metadata: Metadata = { title: "Full leaderboard", description: "Search the GOATLab probabilistic NBA leaderboard with rank bands and evidence statuses." };
export const dynamic = "force-dynamic";
const pageSize = 50;

type SearchParams = Promise<{ search?: string; active?: string; status?: string; page?: string }>;
function href(query: { search: string; active: string; status: string; page: number }): string {
  const params = new URLSearchParams();
  if (query.search) params.set("search", query.search);
  if (query.active) params.set("active", query.active);
  if (query.status) params.set("status", query.status);
  if (query.page > 1) params.set("page", String(query.page));
  return `/leaderboard${params.size ? `?${params}` : ""}`;
}

export default async function FullLeaderboard({ searchParams }: { searchParams: SearchParams }) {
  const raw = await searchParams;
  const search = typeof raw.search === "string" ? raw.search.trim().slice(0, 100) : "";
  const active = raw.active === "true" ? "true" : "";
  const status = (["OFFICIAL", "PROVISIONAL", "INTERVAL_NATIVE"] as const).find((value) => value === raw.status) ?? "";
  const requested = Number(raw.page);
  const page = Number.isSafeInteger(requested) && requested > 0 ? Math.min(requested, 1000) : 1;
  const query: LeaderboardQuery = { limit: pageSize, offset: (page - 1) * pageSize };
  if (search) query.search = search;
  if (active) query.active = true;
  if (status) query.status = status;
  const result = await getLeaderboard(query);
  const totalPages = Math.max(1, Math.ceil(result.total / pageSize));
  return <div className="shell interior-page"><header className="interior-header"><p className="eyebrow">THE FULL FIELD</p><h1>Explore the leaderboard.</h1><p>Search calibrated rank distributions across all eligible careers. Filters never alter anyone’s measured value.</p></header>
    <UncertaintyInfo compact />
    <form className="filter-bar" action="/leaderboard" method="get" role="search"><label>Search players<input name="search" type="search" defaultValue={search} placeholder="e.g. Kareem Abdul-Jabbar" autoComplete="off" /></label><label>Career<select name="active" defaultValue={active}><option value="">All careers</option><option value="true">Active only</option></select></label><label>Evidence<select name="status" defaultValue={status}><option value="">All statuses</option><option value="OFFICIAL">Official</option><option value="PROVISIONAL">Provisional</option><option value="INTERVAL_NATIVE">Interval-native</option></select></label><button className="button button--dark" type="submit">Apply filters ↗</button></form>
    <div className="results-bar"><strong>{result.total.toLocaleString()} players</strong><span>{result.total ? `Showing ${result.offset + 1}–${Math.min(result.offset + pageSize, result.total)}` : "No matches"}</span></div>
    {result.entries.length ? <LeaderboardTable entries={result.entries} /> : <div className="empty-state"><h2>{page > totalPages ? "No players on this page" : "No players found"}</h2><p>Try a broader name or remove a filter.</p><Link className="button button--dark" href="/leaderboard">Clear filters</Link></div>}
    <nav className="pagination" aria-label="Leaderboard pages"><span>Page {page} of {totalPages}</span><div>{page > 1 && <Link href={href({ search, active, status, page: page - 1 })}>← Previous</Link>}{page < totalPages && <Link href={href({ search, active, status, page: page + 1 })}>Next →</Link>}</div></nav>
  </div>;
}
