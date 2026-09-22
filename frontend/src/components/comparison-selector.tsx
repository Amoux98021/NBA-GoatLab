"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";
import type { KeyboardEvent } from "react";
import type { PlayerSearchResult } from "@/lib/types";
import { statusLabel } from "@/lib/display";

export type PlayerChoice = PlayerSearchResult;

function PlayerSearch({
  label, value, otherId, onChange,
}: {
  label: string;
  value: PlayerChoice | null;
  otherId: string | null;
  onChange: (player: PlayerChoice | null) => void;
}) {
  const listId = useId();
  const [query, setQuery] = useState(value?.player_name ?? "");
  const [results, setResults] = useState<PlayerChoice[]>([]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (query.trim().length < 2 || (value !== null && query === value.player_name)) return;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      setError("");
      try {
        const response = await fetch(`/api/compare/search?q=${encodeURIComponent(query.trim())}`, { signal: controller.signal });
        if (!response.ok) throw new Error("Search is temporarily unavailable.");
        const body: unknown = await response.json();
        if (!body || typeof body !== "object" || !("entries" in body) || !Array.isArray(body.entries)) throw new Error("Search returned an invalid response.");
        setResults(body.entries as PlayerChoice[]);
        setHighlight(0);
        setOpen(true);
      } catch (reason) {
        if (!controller.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "Search is temporarily unavailable.");
          setResults([]);
          setOpen(false);
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 220);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [query, value]);

  function choose(player: PlayerChoice) {
    if (player.player_id === otherId) {
      setError("Choose a different player for each side.");
      return;
    }
    onChange(player);
    setQuery(player.player_name);
    setResults([]);
    setOpen(false);
    setLoading(false);
    setError("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!open || results.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlight((index) => (index + 1) % results.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlight((index) => (index - 1 + results.length) % results.length);
    } else if (event.key === "Enter") {
      event.preventDefault();
      choose(results[highlight]);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  return <div className="compare-search" onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}>
    <label htmlFor={`${listId}-input`}>{label}</label>
    <input
      id={`${listId}-input`}
      type="search"
      role="combobox"
      aria-autocomplete="list"
      aria-controls={`${listId}-results`}
      aria-expanded={open && results.length > 0}
      aria-activedescendant={open && results.length > 0 ? `${listId}-option-${highlight}` : undefined}
      placeholder="Search a player name"
      autoComplete="off"
      value={query}
      onChange={(event) => { setQuery(event.target.value); onChange(null); setError(""); if (event.target.value.trim().length < 2) { setResults([]); setOpen(false); setLoading(false); } }}
      onKeyDown={onKeyDown}
      onFocus={() => { if (results.length > 0) setOpen(true); }}
    />
    <div className="compare-search__hint" aria-live="polite">{error || (loading ? "Searching canonical player records…" : value ? `${statusLabel(value.ranking_status)} evidence${value.active ? " · active career" : ""}` : "Search by name; select a canonical player record.")}</div>
    {open && results.length > 0 && <ul id={`${listId}-results`} className="compare-search__results" role="listbox" aria-label={`${label} search results`}>
      {results.map((player, index) => <li key={player.player_id} role="presentation"><button
        id={`${listId}-option-${index}`}
        type="button"
        role="option"
        aria-selected={index === highlight}
        disabled={player.player_id === otherId}
        onMouseEnter={() => setHighlight(index)}
        onClick={() => choose(player)}
      ><span>{player.player_name}<small>{player.active === true ? "Active" : player.active === false ? "Retired" : "Career status unknown"} · {statusLabel(player.ranking_status)}</small></span><span>{player.display_position === null ? "Unranked" : `#${player.display_position}`}</span></button></li>)}
    </ul>}
    {open && results.length === 0 && !loading && query.trim().length >= 2 && <p className="compare-search__empty">No rankable player matched that name.</p>}
  </div>;
}

export function ComparisonSelector({ initialA = null, initialB = null }: { initialA?: PlayerChoice | null; initialB?: PlayerChoice | null }) {
  const router = useRouter();
  const [playerA, setPlayerA] = useState<PlayerChoice | null>(initialA);
  const [playerB, setPlayerB] = useState<PlayerChoice | null>(initialB);
  const [message, setMessage] = useState("");
  const [swapCount, setSwapCount] = useState(0);

  function compare() {
    if (!playerA || !playerB) { setMessage("Choose two players before comparing."); return; }
    if (playerA.player_id === playerB.player_id) { setMessage("Choose two different players."); return; }
    setMessage("");
    router.push(`/compare/${encodeURIComponent(playerA.player_id)}/${encodeURIComponent(playerB.player_id)}`);
  }

  function swap() {
    setPlayerA(playerB);
    setPlayerB(playerA);
    setSwapCount((count) => count + 1);
    setMessage("");
  }

  return <div className="compare-selector" data-reveal><div className="compare-selector__inputs">
    <PlayerSearch key={`a-${swapCount}`} label="Player A" value={playerA} otherId={playerB?.player_id ?? null} onChange={(value) => { setPlayerA(value); setMessage(""); }} />
    <button className="compare-selector__swap" type="button" onClick={swap} aria-label="Swap selected players">⇄ <span>Swap</span></button>
    <PlayerSearch key={`b-${swapCount}`} label="Player B" value={playerB} otherId={playerA?.player_id ?? null} onChange={(value) => { setPlayerB(value); setMessage(""); }} />
  </div><div className="compare-selector__footer"><p aria-live="polite">{message || "Search covers the 1,882 distribution-rankable careers. Unavailable profiles can still explain why a comparison cannot be made."}</p><button className="button button--dark" type="button" onClick={compare} disabled={!playerA || !playerB || playerA.player_id === playerB.player_id}>Compare these players ↗</button></div></div>;
}
