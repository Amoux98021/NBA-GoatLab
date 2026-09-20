"use client";
import Link from "next/link";
export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <div className="shell empty-state interior-page" role="alert"><p className="eyebrow">RANKING SERVICE UNAVAILABLE</p><h1>We couldn’t load this page.</h1><p>The frozen release may be temporarily unavailable. No substitute ranking is shown.</p><div className="error-actions"><button className="button button--dark" onClick={reset}>Try again</button><Link className="button button--outline" href="/methodology">Read methodology</Link></div></div>;
}
