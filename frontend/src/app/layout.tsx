import type { Metadata, Viewport } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "GOATLab — Probabilistic NBA GOAT Rankings", template: "%s — GOATLab" },
  description: "GOATLab models the NBA GOAT debate with explicit, auditable assumptions and uncertainty-aware rankings.",
  robots: process.env.GOATLAB_PUBLICATION_RIGHTS_APPROVED === "true"
    ? { index: true, follow: true }
    : { index: false, follow: false, nocache: true },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#162b2c" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" data-scroll-behavior="smooth"><body>
    <a className="skip-link" href="#main-content">Skip to content</a>
    <header className="site-header"><div className="shell site-header__inner"><Link className="brand" href="/" aria-label="GOATLab home"><span className="brand-mark" aria-hidden="true">G<span>·</span></span><span>GOAT<span>Lab</span></span></Link><nav aria-label="Primary navigation"><Link href="/">Top 100</Link><Link href="/leaderboard">All players</Link><Link href="/compare">Compare</Link><Link href="/methodology">Methodology</Link></nav></div></header>
    <main id="main-content">{children}</main>
    <footer className="site-footer"><div className="shell site-footer__inner"><div><span className="footer-brand">GOATLab</span><p>A model of the debate, not a final answer.</p></div><div><p>2025–26 cutoff · careers measured to date</p><p>Probabilistic ranking policy V2 · <Link href="/methodology">How this works ↗</Link></p><p>Display positions summarize uncertainty, not exact scientific order.</p></div></div></footer>
  </body></html>;
}
