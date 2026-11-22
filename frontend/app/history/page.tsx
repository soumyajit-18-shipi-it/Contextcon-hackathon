'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api, RunInput, RunDetail } from '../../lib/api';

type HistoryRow = {
  id: number;
  input: RunInput;
  verdict?: string | null;
  decision?: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  cost_inr: number;
  duplicate_of?: string | null;
  duplicate_run_id?: number | null;
};

const verdictTone = (v?: string | null) =>
  v === 'CLEARED'
    ? 'bg-emerald-100 text-emerald-800 border border-emerald-200'
    : v === 'SUSPECTED FRONT'
    ? 'bg-red-100 text-red-800 border border-red-200'
    : v === 'HOLD FOR REVIEW'
    ? 'bg-amber-100 text-amber-800 border border-amber-200'
    : v === 'CANNOT VERIFY'
    ? 'bg-slate-100 text-slate-800 border border-slate-200'
    : 'bg-slate-100 text-slate-600 border border-slate-200';

export default function History() {
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    api<HistoryRow[]>('/runs')
      .then(async initial => {
        if (!alive) return;
        setRows(initial);
        const recent = initial.slice(0, 50);
        const details = await Promise.all(
          recent.map(async row => {
            try {
              return await api<RunDetail>(`/runs/${row.id}`);
            } catch {
              return null;
            }
          })
        );
        if (!alive) return;
        setRows(current =>
          current.map(row => {
            const index = initial.findIndex(item => item.id === row.id);
            const detail = index < 50 ? details[index] : null;
            const match = detail?.duplicate_matches?.find((item: any) => item.run_id);
            return {
              ...row,
              duplicate_of: detail?.duplicate_of || row.duplicate_of,
              duplicate_run_id: match?.run_id || null
            };
          })
        );
      })
      .catch(e => setError(e.message))
      .finally(() => alive && setLoading(false));

    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="space-y-6">
      {/* Heading */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wider text-indigo-600">Review activity</div>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 mt-1">Run history</h1>
          <p className="text-sm text-slate-500 mt-1">A record of vendor checks, decisions and duplicate links.</p>
        </div>
        <Link
          href="/"
          className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors"
        >
          <span>Start new review</span>
          <span aria-hidden="true">→</span>
        </Link>
      </div>

      {error && (
        <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
          Could not load history: {error}
        </p>
      )}

      {/* History Table Card */}
      <section className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-6 py-4">
          <div>
            <h2 className="text-base font-bold text-slate-900">Verification runs</h2>
            <p className="mt-0.5 text-xs text-slate-500">
              {loading ? 'Loading records…' : `${rows.length} ${rows.length === 1 ? 'run' : 'runs'}`}
            </p>
          </div>
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
            Most recent first
          </span>
        </div>

        {rows.length > 0 && (
          <div className="overflow-auto">
            <table className="w-full min-w-[850px] text-left text-sm">
              <thead className="bg-slate-50/80 border-b border-slate-100 text-xs font-semibold uppercase tracking-wider text-slate-500">
                <tr>
                  {['Vendor', 'Verdict', 'Decision', 'Status', 'Date', 'Cost', 'Duplicate', ''].map((x, i) => (
                    <th key={i} className="px-5 py-3.5">
                      {x}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map(r => (
                  <tr key={r.id} className="transition-colors hover:bg-slate-50/70">
                    <td className="px-5 py-4">
                      <div className="font-semibold text-slate-900">{r.input?.name || `Run ${r.id}`}</div>
                      <div className="mt-0.5 text-xs text-slate-400">Run #{r.id}</div>
                    </td>
                    <td className="px-5 py-4">
                      <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${verdictTone(r.verdict)}`}>
                        {r.verdict || 'Pending'}
                      </span>
                    </td>
                    <td className="px-5 py-4 text-slate-700 font-medium">{r.decision || 'Pending'}</td>
                    <td className="px-5 py-4">
                      <span className="inline-flex items-center gap-2 text-slate-600 text-xs">
                        <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
                        {r.status}
                      </span>
                    </td>
                    <td className="px-5 py-4 text-xs text-slate-500">{r.created_at}</td>
                    <td className="px-5 py-4 tabular-nums font-medium text-slate-700 text-xs">
                      ₹{Number(r.cost_inr || 0).toFixed(2)}
                    </td>
                    <td className="px-5 py-4 text-xs">
                      {r.duplicate_run_id ? (
                        <Link className="font-semibold text-indigo-600 hover:text-indigo-800 hover:underline" href={`/runs/${r.duplicate_run_id}`}>
                          Earlier run #{r.duplicate_run_id}
                        </Link>
                      ) : r.duplicate_of ? (
                        <span className="text-slate-600">Client vendor {r.duplicate_of}</span>
                      ) : (
                        <span className="text-slate-300">—</span>
                      )}
                    </td>
                    <td className="px-5 py-4 text-right">
                      <Link
                        className="whitespace-nowrap font-semibold text-indigo-600 hover:text-indigo-800 text-xs inline-flex items-center gap-1 hover:underline"
                        href={`/runs/${r.id}`}
                      >
                        Open review <span aria-hidden="true">→</span>
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {loading && (
          <div role="status" className="px-5 py-16 text-center">
            <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-indigo-200 border-t-indigo-600" />
            <p className="mt-3 text-sm text-slate-500">Loading runs…</p>
          </div>
        )}

        {!loading && !error && !rows.length && (
          <div className="px-5 py-16 text-center">
            <p className="font-semibold text-slate-900">No reviews yet</p>
            <p className="mt-1 text-sm text-slate-500">New vendor checks will appear here.</p>
            <Link href="/" className="mt-4 inline-flex font-semibold text-indigo-600 hover:underline text-sm">
              Start a review →
            </Link>
          </div>
        )}
      </section>
    </div>
  );
}
