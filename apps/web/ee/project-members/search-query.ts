export const MIN_SEARCH_CHARS = 3;

export const normalizeQuery = (q: string): string => q.trim();

export const shouldSearch = (q: string): boolean => normalizeQuery(q).length >= MIN_SEARCH_CHARS;
