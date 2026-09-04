import { promises as fs } from 'node:fs';
import path from 'node:path';

const ROOT = path.join(process.cwd(), 'data', 'reentry');
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const DATA_BASE =
  process.env.REENTRY_DATA_BASE_URL ??
  'https://raw.githubusercontent.com/arjunthak0522/swing-intelligence/main/data/reentry';

async function readLocalJson<T>(relativePath: string): Promise<T> {
  const raw = await fs.readFile(path.join(ROOT, relativePath), 'utf8');
  return JSON.parse(raw) as T;
}

async function readLiveJson<T>(relativePath: string): Promise<T> {
  const url = `${DATA_BASE}/${relativePath}`;
  try {
    const response = await fetch(url, {
      next: { revalidate: 60 },
      headers: { Accept: 'application/json' },
    });
    if (response.ok) {
      return (await response.json()) as T;
    }
    if (response.status === 404) {
      throw new Error('Not found');
    }
    throw new Error(`Live data request failed with HTTP ${response.status}`);
  } catch (error) {
    // Bundled data is a resilience fallback only. The normal path is GitHub main,
    // which lets the app update after each completed-close engine run without a rebuild.
    try {
      return await readLocalJson<T>(relativePath);
    } catch {
      throw error;
    }
  }
}

export function assertDate(value: string | null): string {
  if (!value || !DATE_RE.test(value)) {
    throw new Error('A valid date in YYYY-MM-DD format is required');
  }
  return value;
}

export async function getLatest() {
  return readLiveJson<Record<string, unknown>>('latest.json');
}

export async function getHistory() {
  return readLiveJson<Array<Record<string, unknown>>>('index.json');
}

export async function getSnapshot(date: string) {
  return readLiveJson<Record<string, unknown>>(`history/${assertDate(date)}.json`);
}

export async function getAnalogs(date: string) {
  const snapshot = await getSnapshot(date);
  return {
    as_of: snapshot.as_of,
    engine_version: snapshot.engine_version,
    analog_count: snapshot.analog_count,
    analogs: snapshot.analogs,
  };
}

export async function getRealized(date: string) {
  return readLiveJson<Record<string, unknown>>(`realized/${assertDate(date)}.json`);
}

export function apiError(error: unknown) {
  const message = error instanceof Error ? error.message : 'Unknown error';
  const notFound = message === 'Not found' || message.includes('ENOENT');
  return Response.json(
    { error: notFound ? 'Not found' : message },
    { status: notFound ? 404 : 400, headers: { 'Cache-Control': 'no-store' } },
  );
}

export function json(data: unknown) {
  return Response.json(data, {
    headers: {
      'Cache-Control': 'public, max-age=0, s-maxage=60, stale-while-revalidate=300',
    },
  });
}
