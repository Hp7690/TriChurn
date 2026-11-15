import { useCallback, useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { DataModeBanner } from '../components/DataModeBanner';
import { Drawer } from '../components/Drawer';
import { ErrorBoundary } from '../components/ErrorBoundary';
import { Sidebar } from '../components/Sidebar';
import { Topbar } from '../components/Topbar';

export function AppLayout() {
  const [menuOpen, setMenuOpen] = useState(false);
  const { pathname } = useLocation();
  const closeMenu = useCallback(() => setMenuOpen(false), []);

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  return (
    <div className="min-h-screen">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-lg focus:bg-surface focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-brand-700 focus:shadow-lg"
      >
        Skip to main content
      </a>
      <aside className="hidden lg:fixed lg:inset-y-0 lg:left-0 lg:z-40 lg:flex lg:w-64">
        <Sidebar />
      </aside>
      <Drawer open={menuOpen} onClose={closeMenu} title="Navigation" side="left" bare>
        <Sidebar onNavigate={closeMenu} />
      </Drawer>
      <div className="lg:pl-64">
        <DataModeBanner />
        <Topbar onOpenMenu={() => setMenuOpen(true)} />
        <main id="main-content" tabIndex={-1} className="mx-auto max-w-[1440px] px-4 py-8 outline-none sm:px-6 lg:px-8">
          <ErrorBoundary key={pathname}>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
