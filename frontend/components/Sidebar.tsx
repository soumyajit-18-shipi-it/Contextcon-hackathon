'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function Sidebar() {
  const pathname = usePathname();
  const isNew = pathname === '/';
  const isHistory = pathname.startsWith('/history');

  return (
    <>
      {/* Mobile top nav */}
      <div className="md:hidden bg-[#0B0F19] text-white px-4 py-3 flex items-center justify-between border-b border-slate-800/80">
        <Link href="/" className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-sm">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          </div>
          <span className="font-bold text-base tracking-tight text-white">Verity</span>
        </Link>
        <div className="flex items-center gap-2">
          <Link
            href="/"
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
              isNew ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            New check
          </Link>
          <Link
            href="/history"
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
              isHistory ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            History
          </Link>
        </div>
      </div>

      {/* Desktop Sidebar */}
      <aside className="w-60 min-w-[240px] hidden md:flex flex-col justify-between bg-[#0B0F19] text-slate-300 p-6 flex-shrink-0 min-h-screen">
        <div>
          {/* Brand */}
          <Link href="/" className="flex items-center gap-3 mb-8">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow-md shadow-indigo-900/40">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <span className="text-xl font-bold tracking-tight text-white">Verity</span>
          </Link>

          {/* Navigation */}
          <nav className="space-y-1.5" aria-label="Main Navigation">
            <Link
              href="/"
              className={`flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-semibold transition-colors ${
                isNew
                  ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-900/30'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
              }`}
            >
              <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
              </svg>
              <span>New check</span>
            </Link>

            <Link
              href="/history"
              className={`flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-semibold transition-colors ${
                isHistory
                  ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-900/30'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
              }`}
            >
              <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>History</span>
            </Link>
          </nav>
        </div>

        {/* Footer info */}
        <div className="pt-6 border-t border-slate-800/80">
          <p className="text-xs text-slate-500 font-medium leading-relaxed">
            Trusted verification.<br />Safer business.
          </p>
        </div>
      </aside>
    </>
  );
}
