'use client';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import SourceViewer from '../../../components/SourceViewer';
import { api, RunDetail, LedgerRow } from '../../../lib/api';

const ORDER = [
  'intake',
  'resolve',
  'duplicate',
  'company',
  'director',
  'site',
  'core_checks',
  'lookalike',
  'copied_site',
  'media',
  'timeline',
  'verdict',
  'explain',
  'report'
];

const GROUPS = ['Identity', 'Activity', 'Director', 'Duplicate', 'Domain', 'Website', 'Media', 'Timeline'];

const badge = (v: string) =>
  v === 'CLEARED'
    ? 'bg-emerald-100 text-emerald-800 border border-emerald-200'
    : v === 'SUSPECTED FRONT'
    ? 'bg-red-100 text-red-800 border border-red-200'
    : v === 'HOLD FOR REVIEW'
    ? 'bg-amber-100 text-amber-800 border border-amber-200'
    : 'bg-slate-100 text-slate-800 border border-slate-200';

const stepLabel = (x: string) => x.replaceAll('_', ' ');

function EvidenceCard({ e, onSource }: { e: any; onSource: (e: any) => void }) {
  return (
    <article id={`e-${e.id}`} className="scroll-mt-5 rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h4 className="font-semibold text-slate-900 text-sm">{e.claim || stepLabel(e.check)}</h4>
          <p className="mt-0.5 text-xs text-slate-500">
            {stepLabel(e.check)} · record date {e.record_date || 'not supplied'}
          </p>
        </div>
        <div className="flex gap-1.5 text-xs">
          <span
            className={`rounded-lg px-2 py-0.5 font-semibold ${
              e.flag === 'hard'
                ? 'bg-red-100 text-red-800 border border-red-200'
                : e.flag === 'soft'
                ? 'bg-amber-100 text-amber-800 border border-amber-200'
                : 'bg-slate-100 text-slate-700 border border-slate-200'
            }`}
          >
            {e.flag || 'none'}
          </span>
          <span
            className={`rounded-lg px-2 py-0.5 font-semibold ${
              e.status === 'verified'
                ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                : e.status === 'unknown'
                ? 'bg-amber-50 text-amber-800 border border-amber-200'
                : 'bg-slate-100 text-slate-700 border border-slate-200'
            }`}
          >
            {e.status}
          </span>
        </div>
      </div>
      <p className="mt-3 break-words text-xs text-slate-700 leading-relaxed">
        {e.status === 'cant_verify'
          ? `I can't verify: ${e.missing || 'the source did not return this fact.'}`
          : e.status === 'unknown'
          ? `Source timed out, retried 2×, held for a person. ${e.missing || ''}`
          : typeof e.value === 'string'
          ? e.value
          : JSON.stringify(e.value ?? '—')}
      </p>
      {e.source_id && (
        <button
          onClick={() => onSource(e)}
          className="mt-3 text-xs font-semibold text-indigo-600 hover:text-indigo-800 underline underline-offset-2"
        >
          View source →
        </button>
      )}
    </article>
  );
}

function CitedExplanation({ text, evidence }: { text: string; evidence: any[] }) {
  const sentences = text.split(/(?<=[.!?])\s+/).filter(Boolean);
  const available = new Set(evidence.map(e => String(e.id)));
  return (
    <div className="mt-2 space-y-2 text-sm leading-relaxed text-slate-700">
      {sentences.map((sentence, i) => {
        const matches = [...sentence.matchAll(/#(\d+)|evidence(?:\s+id)?\s*[:#]?\s*(\d+)/gi)]
          .map(m => m[1] || m[2])
          .filter(id => available.has(id));
        return (
          <p key={i}>
            {sentence}
            {matches.map(id => (
              <button
                key={id}
                className="ml-2 font-semibold text-indigo-600 hover:text-indigo-800 underline text-xs"
                onClick={() => document.getElementById(`e-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })}
              >
                Evidence #{id}
              </button>
            ))}
          </p>
        );
      })}
    </div>
  );
}

export default function RunPage() {
  const params = useParams<{ id: string }>();
  const id = String(params.id);
  const [data, setData] = useState<RunDetail>();
  const [ledgerRows, setLedgerRows] = useState<LedgerRow[]>([]);
  const [credits, setCredits] = useState<any>();
  const [creditError, setCreditError] = useState('');
  const [ledgerError, setLedgerError] = useState('');
  const [error, setError] = useState('');
  const [decision, setDecision] = useState<'clear' | 'reject'>('clear');
  const [reason, setReason] = useState('');
  const [reviewer, setReviewer] = useState('');
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<any>();
  const [pollEpoch, setPollEpoch] = useState(0);
  const [tab, setTab] = useState<'report' | 'ledger'>('report');
  const [missing, setMissing] = useState({ name: '', website: '' });

  const refresh = useCallback(async () => {
    const x = await api<RunDetail>(`/runs/${id}`);
    setData(x);
    return x;
  }, [id]);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      try {
        const x = await api<RunDetail>(`/runs/${id}`);
        if (!alive) return;
        setData(x);
        setError('');
        api<{ rows: LedgerRow[] }>(`/ledger?run_id=${id}`)
          .then(l => {
            if (alive) {
              setLedgerRows(l.rows || []);
              setLedgerError('');
            }
          })
          .catch(e => alive && setLedgerError(e.message));
        if (['queued', 'running'].includes(x.run.status)) {
          timer = setTimeout(poll, 2000);
        }
      } catch (e: any) {
        if (alive) {
          setError(e.message);
          timer = setTimeout(poll, 5000);
        }
      }
    };
    poll();
    api('/credits')
      .then(x => {
        if (alive) {
          setCredits(x);
          setCreditError('');
        }
      })
      .catch(e => alive && setCreditError(e.message));
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [id, pollEpoch]);

  const evidence = data?.evidence || [];
  const steps = data?.steps || [];
  const run = data?.run!;
  const used = new Set(steps.map(s => s.step_name));
  const reasons = Array.isArray(data?.verdict?.reasons) ? data?.verdict.reasons : [];
  const answers = [
    ['Who runs it?', 'who_runs_it'],
    ['How long has it existed?', 'how_long_it_has_existed'],
    ['Is it trading?', 'is_it_trading'],
    ['What looks off?', 'what_looks_off']
  ];
  const sortedTimeline = useMemo(
    () => [...(data?.timeline || [])].sort((a, b) => String(a.date || '').localeCompare(String(b.date || ''))),
    [data?.timeline]
  );

  async function selectCandidate(index: number) {
    setBusy(true);
    setError('');
    try {
      await api(`/runs/${id}/select-candidate`, { method: 'POST', body: JSON.stringify({ index }) });
      await refresh();
      setPollEpoch(v => v + 1);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function provideInput() {
    const body: any = {};
    if (missing.name.trim()) body.name = missing.name.trim();
    if (missing.website.trim()) body.website = missing.website.trim();
    if (!body.name && !body.website) {
      setError('Enter the vendor name or website.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await api(`/runs/${id}/input`, { method: 'POST', body: JSON.stringify(body) });
      await refresh();
      setPollEpoch(v => v + 1);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (reason.trim().length < 3) {
      setError('Enter a reason (at least 3 characters).');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await api(`/runs/${id}/approve`, {
        method: 'POST',
        body: JSON.stringify({ decision, reason: reason.trim(), user: reviewer.trim() })
      });
      await refresh();
    } catch (e: any) {
      if (e.status === 409) {
        const existing = e.detail?.approval;
        setError(existing ? `Already decided by ${existing.user} at ${existing.ts}.` : `Already decided: ${e.message}`);
        try {
          await refresh();
        } catch {}
      } else setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (!data) {
    return (
      <div className="space-y-6">
        <section className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-8">
          <p className="text-[11px] font-bold uppercase tracking-wider text-indigo-600">Vendor review</p>
          <p role="status" className="mt-3 text-sm text-slate-600">
            {error ? `Could not load this run: ${error}` : 'Loading check…'}
          </p>
        </section>
      </div>
    );
  }

  const verdict = typeof data.verdict === 'string' ? data.verdict : data.verdict?.verdict;
  const terminal = !['queued', 'running'].includes(run.status);
  const spent = Number(run.elapsed_s || 0);
  const route = (x: any) => String(x.check || '').toLowerCase();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-wider text-indigo-600">
            Vendor review · Run #{id}
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 mt-1">
            {run?.input?.name || `Run ${id}`}
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            {run?.status} · {run?.created_at}
          </p>
        </div>
        <Link
          href="/history"
          className="inline-flex items-center gap-1.5 text-sm font-semibold text-indigo-600 hover:text-indigo-800 hover:underline"
        >
          ← Review history
        </Link>
      </div>

      {error && (
        <div role="alert" className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
          {error}
        </div>
      )}

      {run.status === 'failed' && (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-950">
          <b>Run failed.</b> {run.status_reason || 'The backend did not supply a failure reason.'}
        </div>
      )}

      {data.duplicate_of && (
        <section className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-950">
          <b>Duplicate match.</b> Matches existing vendor {data.duplicate_of} in client records.
        </section>
      )}

      {data.duplicate_matches?.length > 0 && (
        <section className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-950">
          <b>Possible duplicate matches</b>
          {data.duplicate_matches.map((m: any, i: number) => (
            <p key={i} className="mt-2 text-sm">
              {m.name || m.vendor_name || JSON.stringify(m)}{' '}
              {m.run_id && (
                <a className="ml-2 underline text-indigo-600" href={`/runs/${m.run_id}`}>
                  Open earlier run →
                </a>
              )}
              {m.source_id && (
                <button className="ml-2 underline text-indigo-600" onClick={() => setSelected({ source_id: m.source_id })}>
                  View record source →
                </button>
              )}
            </p>
          ))}
        </section>
      )}

      {/* Tabs */}
      <nav className="flex gap-2" aria-label="Run views">
        <button
          onClick={() => setTab('report')}
          className={`rounded-xl px-4 py-2 text-sm font-semibold transition-colors ${
            tab === 'report'
              ? 'bg-indigo-600 text-white shadow-sm'
              : 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
          }`}
        >
          Report
        </button>
        <button
          onClick={() => setTab('ledger')}
          className={`rounded-xl px-4 py-2 text-sm font-semibold transition-colors ${
            tab === 'ledger'
              ? 'bg-indigo-600 text-white shadow-sm'
              : 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
          }`}
        >
          Cost ledger ({ledgerRows.length})
        </button>
      </nav>

      {tab === 'report' ? (
        <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="space-y-6">
            {verdict && (
              <section className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
                <div className="flex flex-wrap items-center gap-3">
                  <span className={`rounded-full px-4 py-1.5 text-xs font-bold ${badge(verdict)}`}>
                    {verdict}
                  </span>
                  <span className="text-sm font-medium text-slate-600">
                    {reasons[0] || run?.status_reason || 'Decision is based on the evidence shown below.'}
                  </span>
                </div>
                {reasons.length > 1 && (
                  <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-slate-600">
                    {reasons.slice(1).map((r: string, i: number) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                )}
                {data.answers && (
                  <div className="mt-5 grid gap-3 sm:grid-cols-2">
                    {answers.map(([label, key]) => {
                      const a = data.answers[key];
                      return (
                        <article key={key} className="rounded-xl border border-slate-100 bg-slate-50/80 p-4">
                          <h3 className="text-[11px] font-bold uppercase tracking-wider text-slate-500">{label}</h3>
                          <p className="mt-2 text-xs leading-relaxed text-slate-800">
                            {a?.text || 'No supported answer is available.'}
                          </p>
                          {(a?.evidence_ids || []).map((eid: number) => (
                            <button
                              key={eid}
                              onClick={() =>
                                document.getElementById(`e-${eid}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
                              }
                              className="mr-2 mt-2 inline-block text-[11px] font-semibold text-indigo-600 hover:underline"
                            >
                              Evidence #{eid}
                            </button>
                          ))}
                        </article>
                      );
                    })}
                  </div>
                )}
                <div className="mt-5 rounded-xl border border-indigo-100 bg-indigo-50/60 p-4">
                  <h3 className="text-sm font-bold text-slate-900">Explanation</h3>
                  {data.explanation ? (
                    <CitedExplanation
                      text={typeof data.explanation === 'string' ? data.explanation : JSON.stringify(data.explanation)}
                      evidence={evidence}
                    />
                  ) : (
                    <p className="mt-1 text-xs text-slate-600">
                      {reasons.join(' ') || 'No explanation was returned by the backend.'}
                    </p>
                  )}
                </div>
                {data.report_md && (
                  <details className="mt-4">
                    <summary className="cursor-pointer text-xs font-semibold text-slate-700 hover:text-indigo-600">
                      Full report
                    </summary>
                    <pre className="mt-2 whitespace-pre-wrap rounded-xl border border-slate-100 bg-slate-50 p-4 text-[11px] text-slate-800">
                      {data.report_md}
                    </pre>
                  </details>
                )}
              </section>
            )}

            {['queued', 'running', 'held', 'awaiting_candidate', 'awaiting_input'].includes(run?.status) && (
              <section className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
                <div className="flex flex-wrap justify-between gap-3">
                  <div>
                    <h2 className="text-base font-bold text-slate-900">
                      Run progress · {run.current_step ? stepLabel(run.current_step) : run.status}
                    </h2>
                    <p className="mt-0.5 text-xs text-slate-500">
                      {run.status_reason || 'Processing in order; completed steps are checkpointed.'}
                    </p>
                  </div>
                  <span className="text-xs font-semibold text-slate-600">
                    {spent.toFixed(1)}s / {run.time_limit_s}s
                  </span>
                </div>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="h-full bg-indigo-600 transition-all duration-300"
                    style={{ width: `${Math.min(100, (spent / Math.max(run.time_limit_s, 1)) * 100)}%` }}
                  />
                </div>
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  {ORDER.map(name => {
                    const item = steps.find(s => s.step_name === name);
                    const status = item?.status || (used.has(name) ? 'done' : 'pending');
                    return (
                      <div key={name} className="flex justify-between rounded-xl bg-slate-50 px-3.5 py-2 text-xs">
                        <span className="font-medium text-slate-700">{stepLabel(name)}</span>
                        <span className="text-slate-500 font-medium">
                          {status}
                          {item?.attempts > 1 ? ` · ${item.attempts} attempts` : ''}
                        </span>
                      </div>
                    );
                  })}
                </div>
                <div className="mt-4 grid grid-cols-2 gap-3 text-xs text-slate-600">
                  <p>
                    Credits: <b className="text-slate-900">{run.credits_used}</b> / {run.credit_limit}
                  </p>
                  <p>
                    Spend: <b className="text-slate-900">₹{Number(run.cost_inr).toFixed(2)}</b> / ₹{run.cost_limit_inr}
                  </p>
                </div>
                {steps.some(s => s.status === 'failed') && (
                  <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
                    One or more steps failed after retry. Their evidence must be treated as unknown.
                  </p>
                )}
                {!terminal && <p className="mt-3 text-xs text-slate-400">Refreshing every 2 seconds.</p>}
              </section>
            )}

            {run.status === 'awaiting_input' && (
              <section className="rounded-2xl border border-amber-200 bg-amber-50/70 p-6 shadow-sm">
                <h2 className="text-base font-bold text-amber-950">More information needed</h2>
                <p className="my-2 text-xs text-amber-900">
                  {run.status_reason || 'The request did not name the vendor or its website.'}
                </p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="text-xs font-semibold text-slate-700">
                    Vendor name
                    <input
                      value={missing.name}
                      onChange={e => setMissing({ ...missing, name: e.target.value })}
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs text-slate-800"
                    />
                  </label>
                  <label className="text-xs font-semibold text-slate-700">
                    Website
                    <input
                      value={missing.website}
                      onChange={e => setMissing({ ...missing, website: e.target.value })}
                      className="mt-1 w-full rounded-xl border border-slate-200 bg-white p-2.5 text-xs text-slate-800"
                      placeholder="https://"
                    />
                  </label>
                </div>
                <button
                  disabled={busy}
                  onClick={provideInput}
                  className="mt-4 rounded-xl bg-indigo-600 hover:bg-indigo-700 px-5 py-2.5 text-xs font-semibold text-white shadow-sm transition disabled:opacity-50"
                >
                  Continue the check
                </button>
              </section>
            )}

            {run.status === 'awaiting_candidate' && (
              <section className="rounded-2xl border border-amber-200 bg-amber-50/70 p-6 shadow-sm">
                <h2 className="text-base font-bold text-amber-950">Choose the matching company</h2>
                <p className="my-2 text-xs text-amber-900">
                  Several candidates matched. Select the correct entity to continue.
                </p>
                {(data.candidates || []).map((c: any, i: number) => (
                  <button
                    disabled={busy}
                    onClick={() => selectCandidate(i)}
                    key={i}
                    className="mb-2 block w-full rounded-xl border border-slate-200 bg-white p-4 text-left text-xs transition hover:border-indigo-300 disabled:opacity-50"
                  >
                    <b className="text-slate-900">{c.name || `Candidate ${i + 1}`}</b>
                    <span className="mt-1 block whitespace-pre-wrap text-slate-600 font-mono text-[11px]">
                      {JSON.stringify(c, null, 2)}
                    </span>
                    <span className="mt-2 block font-semibold text-indigo-600">Select this company →</span>
                  </button>
                ))}
              </section>
            )}

            {evidence.length > 0 && (
              <section className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
                <h2 className="text-base font-bold text-slate-900">Evidence</h2>
                {GROUPS.map(group => {
                  const items = evidence.filter(e => {
                    const c = route(e);
                    if (group === 'Activity') return ['headcount', 'hiring', 'traffic', 'activity', 'trading'].some(k => c.includes(k));
                    if (group === 'Director') return c.includes('director') || c.includes('nominee');
                    if (group === 'Timeline') return c.includes('founded') || c.includes('timeline') || c.includes('age');
                    if (group === 'Identity') return c.includes('resolve') || c.includes('identity') || c.includes('name_location');
                    if (group === 'Duplicate') return c.includes('duplicate');
                    if (group === 'Domain') return c.includes('domain') || c.includes('lookalike');
                    if (group === 'Website') return c.includes('site') || c.includes('copied') || c.includes('template');
                    return c.includes(group.toLowerCase());
                  });
                  if (!items.length) return null;
                  return (
                    <div key={group} className="mt-5">
                      <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">{group}</h3>
                      <div className="space-y-2.5">
                        {items.map(e => (
                          <EvidenceCard key={e.id} e={e} onSource={setSelected} />
                        ))}
                      </div>
                    </div>
                  );
                })}
              </section>
            )}

            {data.media_hits?.length > 0 && (
              <section className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
                <h2 className="text-base font-bold text-slate-900">Media review</h2>
                {data.media_hits.map((h: any, i: number) => (
                  <article
                    key={i}
                    className={`mt-3 rounded-xl p-4 text-xs ${
                      h.label === 'namesake_cleared'
                        ? 'border border-emerald-200 bg-emerald-50'
                        : 'border border-slate-100 bg-slate-50'
                    }`}
                  >
                    <div className="flex justify-between gap-3">
                      <b className="text-slate-900">{h.title || h.label}</b>
                      <span
                        className={`rounded-lg px-2 py-0.5 text-[11px] font-semibold ${
                          h.label === 'namesake_cleared' ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-700'
                        }`}
                      >
                        {h.label || 'unresolved'}
                      </span>
                    </div>
                    <p className="mt-2 text-slate-600">{h.reason || 'No match explanation was supplied.'}</p>
                    {h.url && (
                      <a className="mt-2 inline-block underline text-indigo-600 hover:text-indigo-800" href={h.url} target="_blank" rel="noreferrer">
                        Open article →
                      </a>
                    )}
                  </article>
                ))}
              </section>
            )}

            {((data.lookalike?.findings || data.lookalike || []).length > 0 || evidence.some(e => route(e).includes('lookalike'))) && (
              <section className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
                <h2 className="text-base font-bold text-slate-900">Look-alike review</h2>
                {(data.lookalike?.findings || data.lookalike || []).map((x: any, i: number) => (
                  <div key={i} className="mt-3 rounded-xl border border-slate-100 bg-slate-50 p-4 text-xs">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <p className="text-[10px] uppercase font-bold text-slate-400">Vendor&apos;s website</p>
                        <p className="font-semibold text-slate-800 mt-0.5">{x.vendor_domain || run.input.website || '—'}</p>
                      </div>
                      <div>
                        <p className="text-[10px] uppercase font-bold text-slate-400">Company the name points to</p>
                        <p className="font-semibold text-slate-800 mt-0.5">
                          {x.official_name || '—'} {x.official_domain ? `(${x.official_domain})` : ''}
                        </p>
                      </div>
                    </div>
                    <p className="mt-2.5">
                      <span
                        className={`rounded-lg px-2 py-0.5 text-[11px] font-semibold ${
                          x.result === 'impersonation'
                            ? 'bg-red-100 text-red-800'
                            : x.result === 'mismatch'
                            ? 'bg-amber-100 text-amber-800'
                            : 'bg-emerald-100 text-emerald-800'
                        }`}
                      >
                        {x.result || '—'}
                      </span>
                      {typeof x.distance === 'number' && x.distance >= 0 ? (
                        <span className="ml-2 text-slate-500">edit distance {x.distance}</span>
                      ) : null}
                    </p>
                    <p className="mt-1 text-slate-600">{x.reason}</p>
                  </div>
                ))}
                {evidence.filter(e => route(e).includes('lookalike')).map(e => (
                  <div key={e.id} className="mt-2.5">
                    <EvidenceCard e={e} onSource={setSelected} />
                  </div>
                ))}
              </section>
            )}

            {(data.timeline?.length > 0 || evidence.some(e => route(e).includes('timeline'))) && (
              <section className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
                <h2 className="text-base font-bold text-slate-900">Timeline</h2>
                <ol className="mt-3 space-y-3 border-l-2 border-slate-200 pl-4">
                  {sortedTimeline.map((event: any, i: number) => {
                    const anomaly = evidence.some(e => e.source_id === event.source_id && (e.flag === 'hard' || e.flag === 'soft'));
                    return (
                      <li key={i} className={`relative text-xs ${anomaly ? 'text-red-800' : 'text-slate-700'}`}>
                        <span
                          className={`absolute -left-[22px] top-1 h-2.5 w-2.5 rounded-full ${anomaly ? 'bg-red-600' : 'bg-indigo-600'}`}
                        />
                        <b>{event.date || 'Date not supplied'}</b> · {event.label || event.event || event.claim}
                        {event.source_id && (
                          <button
                            className="ml-2 underline text-indigo-600 hover:text-indigo-800"
                            onClick={() =>
                              setSelected({ source_id: event.source_id, field_path: event.field_path, passage: event.passage })
                            }
                          >
                            Source
                          </button>
                        )}
                      </li>
                    );
                  })}
                </ol>
                {evidence.filter(e => route(e).includes('timeline') || route(e).includes('founded') || route(e).includes('age')).map(e => (
                  <div key={e.id} className="mt-3">
                    <EvidenceCard e={e} onSource={setSelected} />
                  </div>
                ))}
              </section>
            )}

            {evidence.some(e => route(e).includes('copied')) && (
              <section className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
                <h2 className="text-base font-bold text-slate-900">Copied/template website findings</h2>
                <div className="mt-3 space-y-2">
                  {evidence.filter(e => route(e).includes('copied')).map(e => (
                    <EvidenceCard key={e.id} e={e} onSource={setSelected} />
                  ))}
                </div>
              </section>
            )}

            <section className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
              <h2 className="text-base font-bold text-slate-900">Personal data used</h2>
              <p className="my-1.5 text-xs text-slate-500">Only fields needed for this check are stored.</p>
              {data.personal_data?.length ? (
                <div className="overflow-auto">
                  <table className="w-full min-w-[520px] text-left text-xs">
                    <thead>
                      <tr className="border-b border-slate-100 text-slate-400">
                        <th className="p-2.5">Person</th>
                        <th>Field</th>
                        <th>Source</th>
                        <th>Purpose</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {data.personal_data.map((p: any, i: number) => (
                        <tr key={i} className="text-slate-700">
                          <td className="p-2.5 font-medium">{p.person || '—'}</td>
                          <td>{p.field || '—'}</td>
                          <td>
                            {p.source_id ? (
                              <button className="underline text-indigo-600 hover:text-indigo-800" onClick={() => setSelected({ source_id: p.source_id })}>
                                Source #{p.source_id}
                              </button>
                            ) : (
                              '—'
                            )}
                          </td>
                          <td className="text-slate-500">{p.purpose || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-xs text-slate-500">No personal data fields were logged.</p>
              )}
            </section>

            {(run.status === 'awaiting_approval' || data.approval) && (
              <section className="rounded-2xl border-2 border-indigo-600 bg-white p-6 shadow-sm">
                <h2 className="text-base font-bold text-slate-900">{data.approval ? 'Final decision' : 'Human approval required'}</h2>
                {data.approval ? (
                  <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-xs text-emerald-950">
                    <b className="text-sm">Decision recorded: {data.approval.decision}</b>
                    <p className="mt-1">
                      By {data.approval.user} · {data.approval.ts}
                    </p>
                    <p className="mt-1 font-medium">Reason: {data.approval.reason}</p>
                  </div>
                ) : (
                  <>
                    <div className="mt-4 flex flex-wrap gap-3">
                      <button
                        onClick={() => setDecision('clear')}
                        aria-pressed={decision === 'clear'}
                        className={`rounded-xl px-4 py-2.5 text-xs font-semibold transition ${
                          decision === 'clear'
                            ? 'bg-emerald-700 text-white shadow-sm'
                            : 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                        }`}
                      >
                        Clear vendor
                      </button>
                      <button
                        onClick={() => setDecision('reject')}
                        aria-pressed={decision === 'reject'}
                        className={`rounded-xl px-4 py-2.5 text-xs font-semibold transition ${
                          decision === 'reject'
                            ? 'bg-red-700 text-white shadow-sm'
                            : 'border border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                        }`}
                      >
                        Reject vendor
                      </button>
                    </div>
                    <label className="mt-4 block text-xs font-semibold text-slate-700">
                      Reviewer name
                      <input
                        required
                        value={reviewer}
                        onChange={e => setReviewer(e.target.value)}
                        className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-800 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100"
                        placeholder="Name of approving person"
                      />
                    </label>
                    <label className="mt-4 block text-xs font-semibold text-slate-700">
                      Required reason
                      <textarea
                        required
                        minLength={3}
                        value={reason}
                        onChange={e => setReason(e.target.value)}
                        rows={3}
                        className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-800 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100 resize-y"
                        placeholder="Provide the reason for this decision..."
                      />
                    </label>
                    <button
                      disabled={busy || !reviewer.trim() || reason.trim().length < 3}
                      onClick={approve}
                      className="mt-4 rounded-xl bg-indigo-600 hover:bg-indigo-700 px-5 py-3 text-xs font-semibold text-white shadow-sm transition disabled:opacity-50"
                    >
                      {busy ? 'Recording…' : `Confirm ${decision === 'clear' ? 'clearance' : 'rejection'}`}
                    </button>
                    <p className="mt-2 text-xs text-slate-400">The backend records at most one decision per run.</p>
                  </>
                )}
              </section>
            )}
          </div>

          <aside className="space-y-6 xl:sticky xl:top-6">
            <section className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
              <h2 className="text-sm font-bold text-slate-900">Run limits and usage</h2>
              <div className="mt-3 space-y-1.5 text-xs text-slate-600">
                <p>
                  Credits: <b className="text-slate-900">{run.credits_used}</b> / {run.credit_limit}
                </p>
                <p>
                  Spend: <b className="text-slate-900">₹{Number(run.cost_inr).toFixed(2)}</b> / ₹{run.cost_limit_inr}
                </p>
                <p>
                  Time: <b className="text-slate-900">{spent.toFixed(1)}s</b> / {run.time_limit_s}s
                </p>
              </div>
              <div className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-600">
                <b className="text-slate-900">Crustdata balance</b>
                <p className="mt-1 text-slate-500 font-mono text-[11px] break-words">
                  {creditError ? `Unavailable: ${creditError}` : credits ? JSON.stringify(credits) : 'Loading balance…'}
                </p>
              </div>
              <button
                onClick={() => setTab('ledger')}
                className="mt-4 text-xs font-semibold text-indigo-600 hover:text-indigo-800 underline block"
              >
                View call-by-call ledger →
              </button>
            </section>

            <section className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
              <h2 className="text-sm font-bold text-slate-900">Processing steps</h2>
              <div className="mt-3 space-y-2 text-xs">
                {ORDER.map(n => {
                  const s = steps.find(x => x.step_name === n);
                  return (
                    <div className="flex justify-between gap-3 text-slate-700" key={n}>
                      <span className="font-medium">{stepLabel(n)}</span>
                      <span className="text-slate-400 font-medium">{s?.status || 'pending'}</span>
                    </div>
                  );
                })}
              </div>
              <p className="mt-4 border-t border-slate-100 pt-3 text-[11px] text-slate-400">
                {terminal
                  ? 'Polling stopped; this run needs no further automatic refresh.'
                  : 'Refreshes every 2 seconds while queued or running.'}
              </p>
            </section>
          </aside>
        </div>
      ) : (
        <section className="overflow-auto rounded-2xl border border-slate-200/80 bg-white shadow-sm">
          <div className="p-6 border-b border-slate-100">
            <h2 className="text-base font-bold text-slate-900">
              This check: {ledgerRows.reduce((a, x) => a + Number(x.credits || 0), 0)} credits · ₹
              {ledgerRows.reduce((a, x) => a + Number(x.cost_inr || 0), 0).toFixed(2)} · {spent.toFixed(1)} seconds
            </h2>
            <p className="mt-1 text-xs text-slate-500">Per-call costs come from GET /ledger?run_id={id}.</p>
          </div>
          <table className="w-full min-w-[950px] text-left text-xs">
            <thead className="bg-slate-50/80 border-b border-slate-100 uppercase tracking-wider text-[10px] text-slate-500 font-semibold">
              <tr>
                {['Provider', 'Endpoint / model', 'Credits', 'Tokens in', 'Tokens out', 'Cost INR', 'Latency', 'Status', 'Timestamp'].map(
                  x => (
                    <th key={x} className="p-3.5">
                      {x}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {ledgerRows.map((r, i) => (
                <tr key={i} className="hover:bg-slate-50/70 transition-colors">
                  <td className="p-3.5 font-medium">{r.provider}</td>
                  <td>{r.endpoint_or_model}</td>
                  <td>{r.credits}</td>
                  <td>{r.tokens_in}</td>
                  <td>{r.tokens_out}</td>
                  <td className="tabular-nums">₹{Number(r.cost_inr || 0).toFixed(2)}</td>
                  <td>{r.latency_ms ?? '—'} ms</td>
                  <td>{r.http_status ?? '—'}</td>
                  <td className="text-slate-400">{r.ts}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!ledgerRows.length && (
            <p className="p-6 text-xs text-slate-500">
              {ledgerError ? `Could not load ledger: ${ledgerError}` : 'No ledger calls have been recorded for this run.'}
            </p>
          )}
        </section>
      )}

      {selected && (
        <SourceViewer
          sourceId={selected.source_id}
          title={selected.claim || selected.title}
          fieldPath={selected.field_path}
          passage={selected.passage}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
