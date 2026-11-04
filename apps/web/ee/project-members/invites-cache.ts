// Caches only a successful lookup: a rejected promise is dropped so the next caller retries.
export const makeCachedLoader = <T>(load: () => Promise<T>): (() => Promise<T>) => {
  let cached: Promise<T> | undefined;
  return () => {
    if (!cached) {
      const p = load();
      cached = p;
      p.catch(() => {
        if (cached === p) cached = undefined;
      });
    }
    return cached;
  };
};
