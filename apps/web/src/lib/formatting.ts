/** Format a stored UTC instant in the study area's civil time. */
export function formatManila(utc: string): string {
  return new Intl.DateTimeFormat('en-PH', {
    timeZone: 'Asia/Manila', dateStyle: 'medium', timeStyle: 'short',
  }).format(new Date(utc));
}

/** A datetime-local control is interpreted explicitly as Asia/Manila (+08:00). */
export function manilaLocalToUtc(local: string): string {
  const parsed = new Date(`${local}+08:00`);
  if (Number.isNaN(parsed.getTime())) throw new Error('Enter a valid Asia/Manila scenario start.');
  return parsed.toISOString();
}

export function integerSeconds(value: string, multiplier = 1): number {
  if (!/^(0|[1-9]\d*)$/.test(value)) throw new Error('Enter a nonnegative whole number.');
  const amount = Number(value) * multiplier;
  if (!Number.isSafeInteger(amount)) throw new Error('The time or count exceeds the supported integer range.');
  return amount;
}
