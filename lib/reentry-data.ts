import { promises as fs } from 'node:fs';
import path from 'node:path';

const ROOT = path.join(process.cwd(), 'data', 'reentry');
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

async function readJson<T>(filePath: string): Promise<T> {
  const raw = await fs.readFile(filePath, 'utf8');
  return JSON.parse(raw) as T;
}

export function assertDate(value: string | null): string {
  if (!value || !DATE_RE.test(value)) {
    throw new Error('A valid date in YYYY-MM-DD format is required');
  }
  return value;
}

export async function getLatest() {
  return readJson<Record<string, unknown>>(path.join(ROOT, 'latest.json'));
}

export async function getHistory() {
  return readJson<Array<Record<string, unknown>>>(path.join(ROOT, 'index.json'));
}

export async function getSnapshot(date: string) {
  return readJson<Record<string, unknown>>(path.join(ROOT, 'history', `${assertDate(date)}.json`));
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
  return readJson<Record<string, unknown>>(path.join(ROOT, 'realized', `${assertDate(date)}.json`));
}

export function apiError(error: unknown) {
  const message = error instanceof Error ? error.message : 'Unknown error';
  const notFound = message.includes('ENOENT');
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
