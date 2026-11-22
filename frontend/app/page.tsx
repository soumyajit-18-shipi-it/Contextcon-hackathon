'use client';
import { FormEvent, useState } from 'react';
import { api, RunInput } from '../lib/api';

export default function Home() {
  const [form, setForm] = useState({ name: '', website: '', director: '', claimed_year: '', request_text: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError('');
    const name = form.name.trim();
    if (!name && !form.website.trim() && !form.request_text.trim()) {
      setError('Give a vendor name, a website, or the request in your own words.');
      return;
    }
    if (form.website.trim()) {
      try {
        const u = new URL(form.website.trim());
        if (!['http:', 'https:'].includes(u.protocol)) throw new Error();
      } catch {
        setError('Enter a valid website URL beginning with http:// or https://.');
        return;
      }
    }
    const year = form.claimed_year ? Number(form.claimed_year) : null;
    if (year && (!Number.isInteger(year) || year < 1800 || year > new Date().getFullYear())) {
      setError('Enter a valid founding year.');
      return;
    }
    setBusy(true);
    try {
      const input: RunInput = {
        name: name || null,
        website: form.website.trim() || null,
        director: form.director.trim() || null,
        claimed_year: year,
        request_text: form.request_text.trim() || null
      };
      const created = await api<{ id: number | string }>('/runs', { method: 'POST', body: JSON.stringify(input) });
      if (created.id === undefined || created.id === null) throw new Error('The backend response did not include a run ID.');
      window.location.assign(`/runs/${created.id}`);
    } catch (e: any) {
      setError(e.message || 'Could not create run.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Hero Banner Card */}
      <section className="bg-[#EEF2FB] border border-indigo-100 rounded-2xl p-6 sm:p-7 flex flex-wrap items-center justify-between gap-6 shadow-sm">
        <div className="flex flex-wrap items-center gap-6 sm:gap-8">
          <div>
            <h1 className="text-3xl font-extrabold tracking-tight text-slate-900">Verity</h1>
            <p className="text-sm font-medium text-slate-500 mt-0.5">Verify. Trust. Grow.</p>
          </div>
          <div className="hidden sm:block h-10 w-px bg-indigo-200/80" />
          <div>
            <span className="block text-[11px] font-semibold uppercase tracking-wider text-slate-400">Powered by</span>
            <span className="text-base font-bold text-slate-800">Crustdata</span>
          </div>
        </div>

        {/* Feature Pills */}
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex items-center gap-2 bg-white/90 border border-slate-200/80 rounded-xl px-3.5 py-2 text-xs font-semibold text-slate-700 shadow-xs">
            <svg className="w-4 h-4 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
            </svg>
            <span>Company Data</span>
          </div>
          <div className="flex items-center gap-2 bg-white/90 border border-slate-200/80 rounded-xl px-3.5 py-2 text-xs font-semibold text-slate-700 shadow-xs">
            <svg className="w-4 h-4 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
            <span>Director Data</span>
          </div>
          <div className="flex items-center gap-2 bg-white/90 border border-slate-200/80 rounded-xl px-3.5 py-2 text-xs font-semibold text-slate-700 shadow-xs">
            <svg className="w-4 h-4 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            <span>Trading Activity</span>
          </div>
        </div>
      </section>

      {/* Main Form and Why Verity Card */}
      <section className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-6 sm:p-8">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12">
          {/* Left Column: Form */}
          <div className="lg:col-span-7">
            <div className="mb-6">
              <h2 className="text-xl font-bold text-slate-900">New Vendor Verification</h2>
              <p className="mt-1 text-sm text-slate-500">Check if your vendor is real, active and trustworthy.</p>
            </div>

            <form onSubmit={submit} className="space-y-4" aria-busy={busy}>
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                  Vendor name <span className="font-normal text-slate-400">· or give a website / request below</span>
                </label>
                <input
                  autoComplete="organization"
                  value={form.name}
                  onChange={e => setForm({ ...form, name: e.target.value })}
                  className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-slate-800 placeholder-slate-400 transition-colors focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                  placeholder="e.g. ACME Logistics Pvt. Ltd."
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                  Website
                </label>
                <input
                  type="url"
                  autoComplete="url"
                  value={form.website}
                  onChange={e => setForm({ ...form, website: e.target.value })}
                  className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-slate-800 placeholder-slate-400 transition-colors focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                  placeholder="e.g. https://www.acme.com"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                  Director (optional)
                </label>
                <input
                  value={form.director}
                  onChange={e => setForm({ ...form, director: e.target.value })}
                  className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-slate-800 placeholder-slate-400 transition-colors focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                  placeholder="e.g. Rajesh Sharma"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                  Claimed founding year
                </label>
                <input
                  inputMode="numeric"
                  type="number"
                  min="1800"
                  max={new Date().getFullYear()}
                  value={form.claimed_year}
                  onChange={e => setForm({ ...form, claimed_year: e.target.value })}
                  className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-slate-800 placeholder-slate-400 transition-colors focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                  placeholder="e.g. 2018"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                  Request in your own words (optional)
                </label>
                <textarea
                  value={form.request_text}
                  onChange={e => setForm({ ...form, request_text: e.target.value })}
                  rows={3}
                  className="w-full rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-slate-800 placeholder-slate-400 transition-colors focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100 resize-y"
                  placeholder="Any specific details, e.g. Please onboard Delhivery (www.delhivery.com) for the Pune-Delhi lane"
                />
              </div>

              {error && (
                <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-700">
                  {error}
                </p>
              )}

              <div className="pt-2">
                <button
                  type="submit"
                  disabled={busy}
                  className="w-full rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-3 px-5 flex items-center justify-center gap-2 shadow-sm transition-colors disabled:opacity-60 text-sm"
                >
                  {busy ? (
                    <span>Starting verification…</span>
                  ) : (
                    <>
                      <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24">
                        <path d="M8 5v14l11-7z" />
                      </svg>
                      <span>Start verification</span>
                    </>
                  )}
                </button>
                <p className="text-center text-xs text-slate-400 mt-2.5">
                  A person reviews and approves every final decision.
                </p>
              </div>
            </form>
          </div>

          {/* Right Column: Why Verity? */}
          <div className="lg:col-span-5 border-t lg:border-t-0 lg:border-l border-slate-100 pt-8 lg:pt-0 lg:pl-10 flex flex-col items-center justify-center text-center">
            <div className="w-20 h-20 rounded-full bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 mb-4 shadow-xs">
              <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>

            <h3 className="text-lg font-bold text-slate-900">Why Verity?</h3>
            <p className="text-xs text-slate-500 mt-1 max-w-xs leading-relaxed mb-6">
              Get comprehensive vendor verification with Crustdata-powered insights.
            </p>

            <div className="w-full max-w-xs space-y-3.5 text-left">
              <div className="flex items-center gap-3.5">
                <div className="w-9 h-9 rounded-full bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center flex-shrink-0">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                </div>
                <div>
                  <p className="text-xs font-semibold text-slate-800">Evidence for every claim</p>
                </div>
              </div>

              <div className="flex items-center gap-3.5">
                <div className="w-9 h-9 rounded-full bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center flex-shrink-0">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                  </svg>
                </div>
                <div>
                  <p className="text-xs font-semibold text-slate-800">Survives restarts, approves once</p>
                </div>
              </div>

              <div className="flex items-center gap-3.5">
                <div className="w-9 h-9 rounded-full bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center flex-shrink-0">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                  </svg>
                </div>
                <div>
                  <p className="text-xs font-semibold text-slate-800">Transparent cost per check</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
