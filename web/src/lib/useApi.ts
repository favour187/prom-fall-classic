import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";

export interface AsyncState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
}

/** Declarative GET hook with refresh + abort on unmount. */
export function useApi<T>(path: string, deps: unknown[] = []) {
  const [state, setState] = useState<AsyncState<T>>({ data: null, error: null, loading: true });
  const abortRef = useRef<AbortController | null>(null);
  const pathRef = useRef(path);
  pathRef.current = path;

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await api<T>(pathRef.current, { signal: controller.signal });
      setState({ data, error: null, loading: false });
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setState({ data: null, error: err as ApiError, loading: false });
    }
  }, [...deps]);

  useEffect(() => {
    void load();
    return () => abortRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);

  return { ...state, refresh: load };
}

/** Mutation hook (POST/PUT/PATCH/DELETE) with busy/error state. */
export function useMutation<TVars, TResult>(method: "POST" | "PUT" | "PATCH" | "DELETE", path: string) {
  const [state, setState] = useState<AsyncState<TResult>>({ data: null, error: null, loading: false });

  const run = useCallback(
    async (vars?: TVars) => {
      setState({ data: null, error: null, loading: true });
      try {
        const data = await api<TResult>(path, { method, body: vars });
        setState({ data, error: null, loading: false });
        return data;
      } catch (err) {
        const error = err as ApiError;
        setState({ data: null, error, loading: false });
        throw error;
      }
    },
    [method, path]
  );

  return { ...state, run };
}
