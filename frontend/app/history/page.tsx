'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import AppHeader from '../../components/AppHeader';
import { api, RunInput, RunDetail } from '../../lib/api';

type HistoryRow = { id: number; input: RunInput; verdict?: string | null; decision?: string | null; status: string; created_at: string; updated_at: string; cost_inr: number; duplicate_of?: string | null; duplicate_run_id?: number | null };
const verdictTone = (v?: string | null) => v === 'CLEARED' ? 'bg-emerald-50 text-emerald-800' : v === 'SUSPECTED FRONT' ? 'bg-red-50 text-red-800' : v === 'HOLD FOR REVIEW' ? 'bg-amber-50 text-amber-900' : 'bg-slate-100 text-slate-700';

export default function History() {
  const [rows, setRows] = useState<HistoryRow[]>([]), [error, setError] = useState(''), [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    api<HistoryRow[]>('/runs').then(async initial => {
      if (!alive) return;
      setRows(initial);
      const recent = initial.slice(0, 50);
      const details = await Promise.all(recent.map(async row => { try { return await api<RunDetail>(`/runs/${row.id}`); } catch { return null; } }));
      if (!alive) return;
      setRows(current => current.map(row => {
        const index = initial.findIndex(item => item.id === row.id), detail = index < 50 ? details[index] : null;
        const match = detail?.duplicate_matches?.find((item: any) => item.run_id);
        return { ...row, duplicate_of: detail?.duplicate_of || row.duplicate_of, duplicate_run_id: match?.run_id || null };
      }));
    }).catch(e => setError(e.message)).finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, []);

  return <main className="app-shell">
    <AppHeader active="history" />
    <div className="page-heading page-heading-row">
      <div><div className="page-kicker">Review activity</div><h1 className="page-title">Run history</h1><p className="page-lede">A record of vendor checks, decisions and duplicate links.</p></div>
      <Link href="/" className="primary-action inline-flex items-center gap-2 px-4 py-3 text-sm">Start new review <span aria-hidden="true">→</span></Link>
    </div>
    {error && <p role="alert" className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-900">Could not load history: {error}</p>}
    <section className="surface-card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4"><div><h2 className="panel-heading">Verification runs</h2><p className="mt-1 text-xs text-slate-500">{loading ? 'Loading records…' : `${rows.length} ${rows.length === 1 ? 'run' : 'runs'}`}</p></div><span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">Most recent first</span></div>
      {rows.length > 0 && <div className="overflow-auto"><table className="w-full min-w-[850px] text-left text-sm"><thead className="bg-slate-50/80"><tr>{['Vendor', 'Verdict', 'Decision', 'Status', 'Date', 'Cost', 'Duplicate', ''].map((x, i) => <th key={i} className="px-4 py-3">{x}</th>)}</tr></thead><tbody>{rows.map(r => <tr key={r.id} className="border-t border-slate-100 transition-colors hover:bg-slate-50/70"><td className="px-4 py-4"><div className="font-semibold text-slate-800">{r.input?.name || `Run ${r.id}`}</div><div className="mt-1 text-xs text-slate-500">Run #{r.id}</div></td><td className="px-4 py-4"><span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${verdictTone(r.verdict)}`}>{r.verdict || 'Pending'}</span></td><td className="px-4 py-4 text-slate-700">{r.decision || 'Pending'}</td><td className="px-4 py-4"><span className="inline-flex items-center gap-2 text-slate-600"><span className="h-1.5 w-1.5 rounded-full bg-slate-400" />{r.status}</span></td><td className="px-4 py-4 text-slate-600">{r.created_at}</td><td className="px-4 py-4 tabular-nums text-slate-700">₹{Number(r.cost_inr || 0).toFixed(2)}</td><td className="px-4 py-4 text-xs">{r.duplicate_run_id ? <Link className="font-medium text-teal-800 hover:underline" href={`/runs/${r.duplicate_run_id}`}>Earlier run #{r.duplicate_run_id}</Link> : r.duplicate_of ? <span className="text-slate-600">Client vendor {r.duplicate_of}</span> : <span className="text-slate-400">—</span>}</td><td className="px-4 py-4"><Link className="whitespace-nowrap font-semibold text-teal-800 hover:underline" href={`/runs/${r.id}`}>Open review <span aria-hidden="true">→</span></Link></td></tr>)}</tbody></table></div>}
      {loading && <div role="status" className="px-5 py-12 text-center"><div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-teal-800"/><p className="mt-3 text-sm text-slate-500">Loading runs…</p></div>}
      {!loading && !error && !rows.length && <div className="px-5 py-16 text-center"><p className="font-semibold text-slate-800">No reviews yet</p><p className="mt-1 text-sm text-slate-500">New vendor checks will appear here.</p><Link href="/" className="mt-4 inline-flex font-semibold text-teal-800 hover:underline">Start a review →</Link></div>}
    </section>
  </main>;
}
