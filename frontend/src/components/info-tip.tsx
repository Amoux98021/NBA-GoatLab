"use client";

import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { ReactNode } from "react";

export function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  const id = useId();
  const details = useRef<HTMLDetailsElement>(null);
  const trigger = useRef<HTMLElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open || !details.current || !trigger.current || !panel.current) return;
    const anchor = details.current, summary = trigger.current, note = panel.current;
    // Fit the same disclosure panel to its trigger and the currently visible viewport.
    const place = () => {
      const viewport = window.visualViewport;
      const left = viewport?.offsetLeft ?? 0;
      const top = viewport?.offsetTop ?? 0;
      const width = viewport?.width ?? document.documentElement.clientWidth;
      const height = viewport?.height ?? document.documentElement.clientHeight;
      const rect = summary.getBoundingClientRect();
      const margin = 12, gap = 6;
      const panelWidth = Math.min(300, Math.max(0, width - 2 * margin));
      const panelLeft = Math.min(Math.max(rect.left, left + margin), left + width - margin - panelWidth);
      note.style.width = `${panelWidth}px`;
      const roomBelow = top + height - margin - rect.bottom - gap;
      const roomAbove = rect.top - top - margin - gap;
      const above = roomBelow < note.scrollHeight && roomAbove > roomBelow;
      note.style.maxHeight = `${Math.max(0, above ? roomAbove : roomBelow)}px`;
      note.style.left = `${panelLeft}px`;
      note.style.top = `${above ? rect.top - gap - note.offsetHeight : rect.bottom + gap}px`;
      note.dataset.placed = "true";
    };
    const closeOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !anchor.contains(event.target) && !note.contains(event.target)) anchor.open = false;
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    window.visualViewport?.addEventListener("resize", place);
    window.visualViewport?.addEventListener("scroll", place);
    document.addEventListener("pointerdown", closeOutside);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
      window.visualViewport?.removeEventListener("resize", place);
      window.visualViewport?.removeEventListener("scroll", place);
      document.removeEventListener("pointerdown", closeOutside);
    };
  }, [open]);

  return <details ref={details} className="info-tip" onToggle={(event) => setOpen(event.currentTarget.open)} onKeyDown={(event) => {
    if (event.key === "Escape" && details.current?.open) {
      event.stopPropagation();
      details.current.open = false;
      trigger.current?.focus();
    }
  }}>
    <summary ref={trigger} aria-controls={id} aria-label={`About ${label}`}>i</summary>
    {open ? createPortal(<div id={id} ref={panel} className="info-tip__content info-tip__content--floating" role="note">{children}</div>, document.body)
      : <div id={id} className="info-tip__content" role="note">{children}</div>}
  </details>;
}
