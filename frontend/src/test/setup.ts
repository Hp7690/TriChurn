import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { cloneElement, createElement, isValidElement, type ReactElement, type ReactNode } from 'react';
import { afterEach, vi } from 'vitest';

// jsdom has no layout engine: give Recharts a fixed size so charts mount.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;

vi.mock('recharts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('recharts')>();
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactNode }) =>
      createElement(
        'div',
        { style: { width: 800, height: 400 } },
        isValidElement(children)
          ? cloneElement(children as ReactElement<{ width: number; height: number }>, { width: 800, height: 400 })
          : children,
      ),
  };
});

afterEach(() => {
  cleanup();
});
