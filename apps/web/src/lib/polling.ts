export function pollingDelay(status: string, hidden: boolean, failures: number): number {
  if (hidden) return 10_000;
  if (status === 'complete' || status === 'failed' || status === 'cancelled') return 15_000;
  return Math.min(2_000 * 2 ** Math.min(failures, 3), 16_000);
}
