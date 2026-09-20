"use client";

import { useState } from "react";

export function CopyComparisonLink() {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  async function copy() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setState("copied");
    } catch {
      setState("failed");
    }
  }
  return <span className="copy-link"><button className="button button--outline" type="button" onClick={copy}>Copy share link</button><span role="status">{state === "copied" ? "Link copied" : state === "failed" ? "Copy unavailable; use the address bar." : ""}</span></span>;
}
