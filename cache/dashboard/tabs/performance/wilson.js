// tabs/performance/wilson.js — Wilson 95% confidence interval for a binomial proportion.
// Used by the Setup Family Podium to display confidence-interval width per family.
// Pure function, no DOM, no DATA dependency.

export function wilsonCI(wins, n) {
  if (n === 0) return { lo: 0, hi: 0 };
  const z = 1.96, p = wins / n;
  const denom = 1 + z*z/n;
  const center = (p + z*z/(2*n)) / denom;
  const margin = z * Math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denom;
  return { lo: Math.max(0, center - margin), hi: Math.min(1, center + margin) };
}
