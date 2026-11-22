import './globals.css';
import Sidebar from '../components/Sidebar';

export const metadata = {
  title: 'Verity · Vendor verification',
  description: 'Evidence-led vendor verification'
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-[#F4F6FB] text-slate-900 antialiased font-sans min-h-screen">
        <div className="flex flex-col md:flex-row min-h-screen">
          <Sidebar />
          <div className="flex-1 flex flex-col min-w-0 bg-[#F4F6FB]">
            {/* Top right profile bar matching mockup */}
            <header className="h-14 px-6 sm:px-8 flex items-center justify-end">
              <div
                className="w-8 h-8 rounded-full bg-[#0B0F19] text-white font-semibold text-xs flex items-center justify-center shadow-sm"
                title="Signed in as Soumyajit"
                aria-label="User profile"
              >
                S
              </div>
            </header>
            <main className="flex-1 px-4 sm:px-8 pb-12 max-w-7xl w-full mx-auto">
              {children}
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}
