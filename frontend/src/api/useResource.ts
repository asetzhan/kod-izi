import { useCallback, useEffect, useState } from "react";

import { apiGet } from "./client";

interface ResourceState<T> {
  data: T | undefined;
  error: unknown;
  loading: boolean;
}

/** Load a GET endpoint; `reload()` fetches it again. A null path loads nothing. */
export function useResource<T>(path: string | null) {
  const [state, setState] = useState<ResourceState<T>>({
    data: undefined,
    error: undefined,
    loading: path !== null,
  });
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (path === null) return;
    let cancelled = false;
    apiGet<T>(path).then(
      (data) => !cancelled && setState({ data, error: undefined, loading: false }),
      (error: unknown) => !cancelled && setState({ data: undefined, error, loading: false }),
    );
    return () => {
      cancelled = true;
    };
  }, [path, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return { ...state, reload };
}
