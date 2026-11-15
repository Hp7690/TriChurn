import { useCallback, useEffect, useRef, useState } from 'react';
import { toError } from '../services/api/errors';

export interface AsyncState<T> {
  status: 'loading' | 'success' | 'error';
  /** Last successful data; kept while a reload is in flight. */
  data: T | null;
  error: Error | null;
  reload: () => void;
}

interface Snapshot<T> {
  status: AsyncState<T>['status'];
  data: T | null;
  error: Error | null;
}

/**
 * Runs `loader` whenever `deps` change (or `reload()` is called) and ignores
 * results from superseded calls.
 */
export function useAsync<T>(loader: () => Promise<T>, deps: readonly unknown[]): AsyncState<T> {
  const [snapshot, setSnapshot] = useState<Snapshot<T>>({ status: 'loading', data: null, error: null });
  const [nonce, setNonce] = useState(0);
  const loaderRef = useRef(loader);

  useEffect(() => {
    loaderRef.current = loader;
  });

  useEffect(() => {
    let cancelled = false;
    setSnapshot((prev) => ({ status: 'loading', data: prev.data, error: null }));
    loaderRef
      .current()
      .then((data) => {
        if (!cancelled) setSnapshot({ status: 'success', data, error: null });
      })
      .catch((error: unknown) => {
        if (!cancelled) setSnapshot({ status: 'error', data: null, error: toError(error) });
      });
    return () => {
      cancelled = true;
    };
    // `deps` is supplied by the caller; the loader itself is read through a ref.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { ...snapshot, reload };
}
