import { useCallback, useEffect, useRef, useState } from 'react';

export interface AsyncState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  reload: () => void;
}

/** Runs ``fn`` on mount and whenever ``deps`` change; ignores results that arrive after unmount or a newer call. */
export function useAsync<T>(fn: () => Promise<T>, deps: readonly unknown[]): AsyncState<T> {
  const [state, setState] = useState<{ data: T | null; error: Error | null; loading: boolean }>({
    data: null,
    error: null,
    loading: true,
  });
  const [tick, setTick] = useState(0);
  const latest = useRef(0);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  useEffect(() => {
    const id = ++latest.current;
    const counter = latest;
    setState((s) => ({ ...s, loading: true, error: null }));
    fn().then(
      (data) => {
        if (latest.current === id) setState({ data, error: null, loading: false });
      },
      (error: unknown) => {
        if (latest.current === id)
          setState({ data: null, error: error instanceof Error ? error : new Error(String(error)), loading: false });
      },
    );
    return () => {
      counter.current += 1;     // invalidate this request on dependency change / unmount
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { ...state, reload };
}
