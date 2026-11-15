import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { buildCrumbs } from '../components/Breadcrumbs';
import { NAV_GROUPS } from '../components/navConfig';
import { Modal } from '../components/ui/Modal';
import { resolveTheme, setThemePreference, THEME_STORAGE_KEY } from '../theme/themeStore';
import { renderApp } from '../test/utils';

describe('theme store', () => {
  beforeEach(() => setThemePreference('light'));
  afterEach(() => setThemePreference('system'));

  it('resolves system preference from the OS setting', () => {
    expect(resolveTheme('system', true)).toBe('dark');
    expect(resolveTheme('system', false)).toBe('light');
    expect(resolveTheme('dark', false)).toBe('dark');
    expect(resolveTheme('light', true)).toBe('light');
  });

  it('applies the dark class and persists the choice', () => {
    setThemePreference('dark');
    expect(document.documentElement).toHaveClass('dark');
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    setThemePreference('light');
    expect(document.documentElement).not.toHaveClass('dark');
  });

  it('top bar toggle switches theme without needing a provider', async () => {
    renderApp('/dashboard');
    await userEvent.click(await screen.findByRole('button', { name: 'Switch to dark theme' }));
    expect(document.documentElement).toHaveClass('dark');
    expect(screen.getByRole('button', { name: 'Switch to light theme' })).toBeInTheDocument();
  });

  it('settings page offers Light, Dark and System', async () => {
    renderApp('/settings');
    const group = await screen.findByRole('radiogroup', { name: 'Theme' });
    await userEvent.click(within(group).getByRole('radio', { name: 'Dark' }));
    expect(document.documentElement).toHaveClass('dark');
    expect(within(group).getByRole('radio', { name: 'Dark' })).toHaveAttribute('aria-checked', 'true');
  });
});

describe('navigation structure', () => {
  it('groups cover every route exactly once', () => {
    const routes = NAV_GROUPS.flatMap((g) => g.items.map((i) => i.to));
    expect(new Set(routes).size).toBe(routes.length);
    expect(routes).toHaveLength(12);
  });

  it('builds breadcrumbs from the route map without exposing ids', () => {
    expect(buildCrumbs('/dashboard').map((c) => c.label)).toEqual(['Analyze', 'Dashboard']);
    expect(buildCrumbs('/customers/TC-1001').map((c) => c.label)).toEqual(['Analyze', 'Customers', 'Customer details']);
    expect(buildCrumbs('/retention/recommendations/C-001').map((c) => c.label)).toEqual([
      'Act', 'Retention', 'Recommendations', 'Recommendation',
    ]);
    expect(buildCrumbs('/revenue/risk').map((c) => c.label)).toEqual(['Act', 'Revenue', 'Revenue at Risk']);
    expect(buildCrumbs('/nope')).toEqual([]);
  });

  it('renders the breadcrumb trail inside the app shell', async () => {
    renderApp('/customers/TC-1001');
    const trail = await screen.findByRole('navigation', { name: 'Breadcrumb' });
    expect(within(trail).getByText('Customer details')).toHaveAttribute('aria-current', 'page');
  });
});

describe('Modal', () => {
  it('renders an accessible dialog and closes on Escape', async () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Confirm action" description="This cannot be undone.">
        <p>Body</p>
      </Modal>,
    );
    expect(screen.getByRole('dialog', { name: 'Confirm action' })).toBeInTheDocument();
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('renders nothing when closed', () => {
    render(<Modal open={false} onClose={() => undefined} title="Hidden" />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
