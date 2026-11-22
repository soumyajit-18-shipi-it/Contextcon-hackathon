'use client';
import { FormEvent, useState } from 'react';
import AppHeader from '../components/AppHeader';
import { api, RunInput } from '../lib/api';

export default function Home() {
  const [form, setForm] = useState({ name: '', website: '', director: '', claimed_year: '', request_text: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(e: FormEvent) {
    e.preventDefault(); setError('');
    const name = form.name.trim();
    if (!name && !form.website.trim() && !form.request_text.trim()) { setError('Give a vendor name, a website, or the request in your own words.'); return; }
    if (form.website.trim()) {
      try { const u = new URL(form.website.trim()); if (!['http:', 'https:'].includes(u.protocol)) throw new Error(); }
      catch { setError('Enter a valid website URL beginning with http:// or https://.'); return; }
    }
    const year = form.claimed_year ? Number(form.claimed_year) : null;
    if (year && (!Number.isInteger(year) || year < 1800 || year > new Date().getFullYear())) { setError('Enter a valid founding year.'); return; }
    setBusy(true);
    try {
      const input: RunInput = { name: name || null, website: form.website.trim() || null, director: form.director.trim() || null, claimed_year: year, request_text: form.request_text.trim() || null };
      const created = await api<{ id: number | string }>('/runs', { method: 'POST', body: JSON.stringify(input) });
      if (created.id === undefined || created.id === null) throw new Error('The backend response did not include a run ID.');
      window.location.assign(`/runs/${created.id}`);
    } catch (e: any) { setError(e.message || 'Could not create run.'); }
    finally { setBusy(false); }
  }

  return <main className="app-shell">
    <AppHeader active="new" />
    <div className="page-heading">
      <div className="page-kicker">Vendor verification</div>
      <h1 className="page-title">Verify before the first rupee moves.</h1>
      <p className="page-lede">Review a supplier’s identity, activity and ownership. Every supported conclusion should lead back to its evidence.</p>
    </div>
    <div className="home-grid">
      <section className="surface-card new-check-card">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div><h2 className="panel-heading text-lg">Start a vendor review</h2><p className="mt-1 text-sm text-slate-500">Add the details available to your team.</p></div>
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">New check</span>
        </div>
        <form onSubmit={submit} className="space-y-5" aria-busy={busy}>
          <label className="form-label">Vendor name <span className="font-normal text-slate-500">· or give a website / free-text request</span><input autoComplete="organization" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className="form-control" placeholder="Registered or trading name" /></label>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="form-label">Website<input type="url" autoComplete="url" value={form.website} onChange={e => setForm({ ...form, website: e.target.value })} className="form-control" placeholder="https://vendor.in" /></label>
            <label className="form-label">Director<input value={form.director} onChange={e => setForm({ ...form, director: e.target.value })} className="form-control" placeholder="If known" /></label>
          </div>
          <label className="form-label">Claimed founding year<input inputMode="numeric" type="number" min="1800" max={new Date().getFullYear()} value={form.claimed_year} onChange={e => setForm({ ...form, claimed_year: e.target.value })} className="form-control max-w-xs" placeholder="Optional" /></label>
          <label className="form-label">Request context <span className="font-normal text-slate-500">· optional</span><textarea value={form.request_text} onChange={e => setForm({ ...form, request_text: e.target.value })} rows={3} className="form-control resize-y" placeholder="Or just paste the request, e.g. Please onboard Delhivery (www.delhivery.com) for the Pune-Delhi lane" /></label>
          {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900">{error}</p>}
          <div className="flex flex-wrap items-center gap-4 border-t border-slate-100 pt-5">
            <button type="submit" disabled={busy} className="primary-action px-5 py-3 text-sm disabled:opacity-60">{busy ? 'Starting check…' : 'Start vendor check'} <span aria-hidden="true">→</span></button>
            <p className="text-xs text-slate-500">A person reviews and approves every final decision.</p>
          </div>
        </form>
      </section>
      <aside className="home-aside surface-card p-6">
        <div className="mb-5"><div className="page-kicker">How reviews work</div><h2 className="mt-2 panel-heading text-lg">Evidence before conclusions</h2></div>
        <ul className="space-y-5">
          <li className="principle-row"><span className="principle-index">01</span><p className="text-sm leading-6 text-slate-600"><b className="text-slate-900">Traceable facts.</b> Claims connect to source records and dates.</p></li>
          <li className="principle-row"><span className="principle-index">02</span><p className="text-sm leading-6 text-slate-600"><b className="text-slate-900">Unknown stays unknown.</b> A timeout is not a clean result.</p></li>
          <li className="principle-row"><span className="principle-index">03</span><p className="text-sm leading-6 text-slate-600"><b className="text-slate-900">Namesakes get context.</b> Similar names alone are not a match.</p></li>
          <li className="principle-row"><span className="principle-index">04</span><p className="text-sm leading-6 text-slate-600"><b className="text-slate-900">People decide.</b> Approval and rejection require a reason.</p></li>
        </ul>
        <div className="mt-6 rounded-xl bg-[#f3f7f7] p-4"><p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Review standard</p><p className="mt-1 text-sm font-medium leading-6 text-slate-700">No evidence means no claim. Uncertainty stays visible for the reviewer.</p></div>
      </aside>
    </div>
  </main>;
}
