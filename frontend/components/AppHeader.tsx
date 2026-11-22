import Link from 'next/link';

export default function AppHeader({active}:{active:'new'|'history'|'run'}) {
  return <header className="app-topbar">
    <Link href="/" className="brand-lockup" aria-label="Verity home">
      <span className="brand-symbol" aria-hidden="true">V</span>
      <span className="brand-copy"><strong>verity</strong><small>VENDOR ASSURANCE</small></span>
    </Link>
    <nav className="top-navigation" aria-label="Main navigation">
      <Link href="/" aria-current={active==='new'?'page':undefined} className={active==='new'?'nav-current':''}>New review</Link>
      <Link href="/history" aria-current={active==='history'?'page':undefined} className={active==='history'?'nav-current':''}>Review history</Link>
    </nav>
    <div className="topbar-context"><span className="context-dot"/>Evidence-led vendor review</div>
  </header>
}
