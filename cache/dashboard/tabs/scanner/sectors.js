// tabs/scanner/sectors.js — Build the sector-filter chip group at the top
// of the scanner. Owns the #fsSectorGrp DOM region. Walks all rows once,
// collects unique sector prefixes, and injects buttons that call
// window.fsSetSector() (defined in dashboard.html).

const KNOWN_SECTORS = ['TECH', 'AUTO', 'RETAIL', 'CRYPTO', 'FINTECH', 'HEALTHCARE', 'ENERGY', 'INDUSTRIAL', 'FINANCE'];

export function buildSectorChips(allRows) {
  const sectors = new Set();
  allRows.forEach(r => {
    if (r.sector) sectors.add((r.sector || '').split(/[\s/]/)[0].toUpperCase());
  });

  const grp = document.getElementById('fsSectorGrp');
  if (!grp) return;

  // Keep first ALL chip + label; replace rest
  const existing = grp.querySelectorAll('button[data-fss]');
  existing.forEach((b, i) => { if (i > 0) b.remove(); });

  KNOWN_SECTORS.forEach(s => {
    if ([...sectors].some(x => x.includes(s.slice(0, 4)))) {
      const btn = document.createElement('button');
      btn.className   = 'chip';
      btn.dataset.fss = s;
      btn.textContent = s.charAt(0) + s.slice(1).toLowerCase();
      btn.onclick     = () => window.fsSetSector(s);
      grp.appendChild(btn);
    }
  });
}
