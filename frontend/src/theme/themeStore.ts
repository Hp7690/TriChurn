import { useCallback, useSyncExternalStore } from 'react';

export type ThemePreference = 'light' | 'dark' | 'system';
export type ResolvedTheme = 'light' | 'dark';

export const THEME_STORAGE_KEY = 'trichurn-theme';

const PREFERENCES: readonly ThemePreference[] = ['light', 'dark', 'system'];
const listeners = new Set<() => void>();

function isPreference(value: unknown): value is ThemePreference {
  return typeof value === 'string' && (PREFERENCES as readonly string[]).includes(value);
}

function readStored(): ThemePreference {
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isPreference(raw) ? raw : 'system';
  } catch {
    return 'system';
  }
}

function systemPrefersDark(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-color-scheme: dark)').matches
    : false;
}

let preference: ThemePreference = typeof window === 'undefined' ? 'system' : readStored();

export function resolveTheme(pref: ThemePreference, prefersDark: boolean): ResolvedTheme {
  if (pref === 'system') return prefersDark ? 'dark' : 'light';
  return pref;
}

function apply(): void {
  if (typeof document === 'undefined') return;
  document.documentElement.classList.toggle('dark', resolveTheme(preference, systemPrefersDark()) === 'dark');
}

function emit(): void {
  apply();
  listeners.forEach((listener) => listener());
}

export function getThemePreference(): ThemePreference {
  return preference;
}

export function setThemePreference(next: ThemePreference): void {
  preference = next;
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, next);
  } catch {
    /* Storage can be unavailable (private mode); the choice then lasts for this session only. */
  }
  emit();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  let media: MediaQueryList | null = null;
  const onSystemChange = () => {
    if (preference === 'system') emit();
  };
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    media = window.matchMedia('(prefers-color-scheme: dark)');
    media.addEventListener('change', onSystemChange);
  }
  return () => {
    listeners.delete(listener);
    media?.removeEventListener('change', onSystemChange);
  };
}

/** Works without a provider so it can be used in any tree, including tests. */
export function useTheme() {
  const pref = useSyncExternalStore(subscribe, getThemePreference, () => 'system' as ThemePreference);
  const resolved = resolveTheme(pref, systemPrefersDark());
  const toggle = useCallback(() => {
    setThemePreference(resolveTheme(getThemePreference(), systemPrefersDark()) === 'dark' ? 'light' : 'dark');
  }, []);
  return { preference: pref, resolved, setPreference: setThemePreference, toggle };
}

apply();
