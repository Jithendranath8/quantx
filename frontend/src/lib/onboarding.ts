/**
 * First-session checklist state, kept per browser.
 *
 * Visiting a page is the cheapest honest signal that a step was tried; steps
 * with real backend evidence (a funded paper account) use that instead.
 */
const VISITED_KEY = 'quantx_visited_pages';
const DISMISSED_KEY = 'quantx_onboarding_dismissed';

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Storage can be unavailable (private mode); the checklist just won't persist.
  }
}

export function visitedPages(): Set<string> {
  try {
    return new Set(JSON.parse(read(VISITED_KEY) ?? '[]') as string[]);
  } catch {
    return new Set();
  }
}

export function recordVisit(pagePath: string): void {
  const visited = visitedPages();
  if (visited.has(pagePath)) return;
  visited.add(pagePath);
  write(VISITED_KEY, JSON.stringify([...visited]));
}

export function isOnboardingDismissed(): boolean {
  return read(DISMISSED_KEY) === '1';
}

export function setOnboardingDismissed(dismissed: boolean): void {
  write(DISMISSED_KEY, dismissed ? '1' : '0');
}
