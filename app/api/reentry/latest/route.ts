import { apiError, getLatest, json } from '@/lib/reentry-data';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    return json(await getLatest());
  } catch (error) {
    return apiError(error);
  }
}
