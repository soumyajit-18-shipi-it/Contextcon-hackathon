'use client';
import { useEffect, useState } from 'react';
import { api } from '../lib/api';

function pathLines(data: any, path: string) {
  const parts = path
    .replace(/^\$\.?/, '')
    .replace(/\[(\d+)\]/g, '.$1')
    .split('.')
    .filter(Boolean);
  let cur = data;
  const lines: string[] = [];
  for (const part of parts) {
    if (cur == null) break;
    cur = cur[part as any];
    lines.push(`${part}: ${JSON.stringify(cur, null, 2)}`);
  }
  return lines;
}

export default function SourceViewer({
  sourceId,
  fieldPath,
  passage,
  title,
  onClose
}: {
  sourceId: number;
  fieldPath?: string | null;
  passage?: string | null;
  title?: string | null;
  onClose: () => void;
}) {
  const [source, setSource] = useState<any>();
  const [error, setError] = useState('');

  useEffect(() => {
    api(`/sources/${sourceId}`).then(setSource).catch(e => setError(e.message));
  }, [sourceId]);

  useEffect(() => {
    if (source && fieldPath && !source.url) {
      document.getElementById('field-highlight')?.scrollIntoView({ block: 'center' });
    }
  }, [source, fieldPath]);

  const json = source?.raw_response;
  const web = source?.kind === 'web' || Boolean(source?.url);
  const text = typeof json === 'string' ? json : JSON.stringify(json, null, 2);

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-slate-950/40 backdrop-blur-xs"
      role="dialog"
      aria-modal="true"
      aria-label="Evidence source"
      onClick={onClose}
    >
      <section
        className="h-full w-full max-w-2xl overflow-auto bg-white p-6 sm:p-8 shadow-2xl border-l border-slate-200"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-wider text-indigo-600">
              Evidence source #{sourceId}
            </p>
            <h2 className="mt-1 text-lg font-bold text-slate-900">{title || 'Source record'}</h2>
          </div>
          <button
            onClick={onClose}
            className="rounded-xl border border-slate-200 px-3.5 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition"
            aria-label="Close source viewer"
          >
            Close
          </button>
        </div>

        {error && (
          <p className="mt-5 rounded-xl border border-red-200 bg-red-50 p-3 text-xs text-red-800">
            {error}
          </p>
        )}

        {!source && !error && <p className="mt-6 text-xs text-slate-500">Loading source…</p>}

        {source && (
          <>
            <dl className="mt-5 grid grid-cols-2 gap-3 text-xs bg-slate-50 p-4 rounded-xl border border-slate-100">
              <div>
                <dt className="text-slate-400 font-medium">Endpoint</dt>
                <dd className="font-semibold text-slate-800 mt-0.5">{source.endpoint || source.kind || '—'}</dd>
              </div>
              <div>
                <dt className="text-slate-400 font-medium">Retrieved</dt>
                <dd className="font-semibold text-slate-800 mt-0.5">{source.retrieved_at || '—'}</dd>
              </div>
              <div>
                <dt className="text-slate-400 font-medium">Record date</dt>
                <dd className="font-semibold text-slate-800 mt-0.5">{source.record_date || 'Not supplied'}</dd>
              </div>
              <div>
                <dt className="text-slate-400 font-medium">Field path</dt>
                <dd className="font-mono text-indigo-600 mt-0.5">{fieldPath || 'Not supplied'}</dd>
              </div>
            </dl>

            {web ? (
              <>
                <blockquote className="mt-5 rounded-xl border-l-4 border-indigo-600 bg-indigo-50/60 p-4 text-xs text-slate-700 leading-relaxed">
                  {passage || 'No quoted passage was stored with this evidence.'}
                </blockquote>
                {source.url && (
                  <a
                    className="mt-4 inline-block rounded-xl bg-indigo-600 hover:bg-indigo-700 px-4 py-2 text-xs font-semibold text-white shadow-sm transition"
                    href={
                      passage
                        ? `${source.url}#:~:text=${encodeURIComponent(passage.split(/\s+/).slice(0, 8).join(' '))}`
                        : source.url
                    }
                    target="_blank"
                    rel="noreferrer"
                  >
                    Open source passage →
                  </a>
                )}
              </>
            ) : (
              <>
                <h3 className="mt-6 text-xs font-bold uppercase tracking-wider text-slate-400">API response</h3>
                {fieldPath && (
                  <div id="field-highlight" className="mt-2.5 scroll-mt-4 rounded-xl border border-amber-300 bg-amber-50 p-3.5">
                    <b className="text-xs text-amber-950">Evidence field · {fieldPath}</b>
                    <pre className="mt-2 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-amber-900">
                      {pathLines(json, fieldPath).join('\n') || passage || 'Field path not found in stored response.'}
                    </pre>
                  </div>
                )}
                <pre className="mt-3 max-h-[60vh] overflow-auto rounded-xl bg-slate-900 p-4 font-mono text-[11px] text-slate-200">
                  {text || 'No raw response stored.'}
                </pre>
              </>
            )}
          </>
        )}
      </section>
    </div>
  );
}
