import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-8 text-center shadow-sm">
      <h2 className="text-xl font-bold text-slate-900">Page not found</h2>
      <p className="mt-2 text-sm text-slate-500">The requested review or page could not be located.</p>
      <Link href="/" className="mt-4 inline-flex rounded-xl bg-indigo-600 px-4 py-2 text-xs font-semibold text-white shadow-sm hover:bg-indigo-700">
        Return to verification
      </Link>
    </div>
  );
}
