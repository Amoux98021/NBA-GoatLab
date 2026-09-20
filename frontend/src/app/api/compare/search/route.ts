import { NextRequest, NextResponse } from "next/server";
import { ApiError, getLeaderboard } from "@/lib/api";
import type { PlayerSearchResult } from "@/lib/types";

export async function GET(request: NextRequest) {
  const query = request.nextUrl.searchParams.get("q")?.trim().slice(0, 80) ?? "";
  if (query.length < 2) return NextResponse.json({ entries: [] as PlayerSearchResult[] });
  try {
    const page = await getLeaderboard({ search: query, limit: 8, offset: 0 });
    const entries: PlayerSearchResult[] = page.entries.map((entry) => ({
      player_id: entry.player_id,
      player_name: entry.player_name,
      active: entry.active,
      ranking_status: entry.ranking_status,
      display_position: entry.display_position,
    }));
    return NextResponse.json({ release_id: page.release_id, entries });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof ApiError ? error.message : "Player search is temporarily unavailable." },
      { status: error instanceof ApiError ? error.status : 503 },
    );
  }
}
