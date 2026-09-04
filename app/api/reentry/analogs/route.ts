import { apiError, assertDate, getAnalogs, json } from '@/lib/reentry-data';

export const dynamic = 'force-dynamic';

export async function GET(request: Request) {
  try {
    const date = assertDate(new URL(request.url).searchParams.get('date'));
    return json(await getAnalogs(date));
  } catch (error) {
    return apiError(error);
  }
}
