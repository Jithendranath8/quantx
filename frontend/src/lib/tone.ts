export type Tone = 'neutral' | 'positive' | 'negative' | 'warning' | 'info';

/** Tone for a BUY / SELL / WAIT action. */
export function actionTone(action: string): Tone {
  if (action === 'BUY') return 'positive';
  if (action === 'SELL') return 'negative';
  return 'warning';
}
