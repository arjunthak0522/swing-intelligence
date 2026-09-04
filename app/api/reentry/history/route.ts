import { apiError, getHistory, json } from '@/lib/reentry-data';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    return json(await getHistory());
  } catch (error) {
    return apiError(error);
  }
}
