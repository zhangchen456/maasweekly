export function browserTimeZone(): string;
export function formatTimestamp(value: string | number | null | undefined, options?: { locale?: string; timeZone?: string }): string;
export function nextDigestCheck(now?: number): string;
export function startTimeDisplay(win: Window & typeof globalThis): () => void;
