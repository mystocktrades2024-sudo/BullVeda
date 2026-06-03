// lens-icons.jsx — small SVG glyphs per lens (16×16 viewbox, stroke-based)

const LENS_ICONS = {
  overview: (
    <svg viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.4" />
      <path d="M8 4 L8 8 L11 9.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  ),
  plan: (
    <svg viewBox="0 0 16 16" fill="none">
      <rect x="2" y="3" width="12" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.3" />
      <line x1="5" y1="6.5" x2="11" y2="6.5" stroke="currentColor" strokeWidth="1.3" />
      <line x1="5" y1="9.5" x2="11" y2="9.5" stroke="currentColor" strokeWidth="1.3" />
      <circle cx="3.6" cy="6.5" r="0.6" fill="currentColor" />
      <circle cx="3.6" cy="9.5" r="0.6" fill="currentColor" />
    </svg>
  ),
  chart: (
    <svg viewBox="0 0 16 16" fill="none">
      <polyline points="1,12 4,8 7,10 11,4 14,6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
      <line x1="1" y1="14.5" x2="15" y2="14.5" stroke="currentColor" strokeWidth="1" opacity="0.5" />
    </svg>
  ),
  technicals: (
    <svg viewBox="0 0 16 16" fill="none">
      <rect x="2" y="9" width="2" height="5" fill="currentColor" />
      <rect x="5" y="6" width="2" height="8" fill="currentColor" />
      <rect x="8" y="11" width="2" height="3" fill="currentColor" />
      <rect x="11" y="4" width="2" height="10" fill="currentColor" />
    </svg>
  ),
  patterns: (
    <svg viewBox="0 0 16 16" fill="none">
      <path d="M1 12 Q 3 10, 4 11 Q 5 12, 7 8 Q 9 4, 11 9 Q 13 14, 15 6"
            stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinecap="round" />
    </svg>
  ),
  smc: (
    <svg viewBox="0 0 16 16" fill="none">
      <rect x="2" y="6" width="5" height="6" stroke="currentColor" strokeWidth="1.3" />
      <rect x="9" y="3" width="5" height="6" stroke="currentColor" strokeWidth="1.3" />
      <line x1="7" y1="9" x2="9" y2="6" stroke="currentColor" strokeWidth="1.3" />
      <circle cx="11.5" cy="11.5" r="2" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  ),
  investment: (
    <svg viewBox="0 0 16 16" fill="none">
      <path d="M3 13 V5 C 3 3.5 5 2.5 8 2.5 C 11 2.5 13 3.5 13 5 V13" stroke="currentColor" strokeWidth="1.3" />
      <ellipse cx="8" cy="5" rx="5" ry="1.5" stroke="currentColor" strokeWidth="1.3" />
      <line x1="3" y1="9" x2="13" y2="9" stroke="currentColor" strokeWidth="1" opacity="0.5" />
    </svg>
  ),
  risk: (
    <svg viewBox="0 0 16 16" fill="none">
      <path d="M8 2 L14 13 H2 Z" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
      <line x1="8" y1="6.5" x2="8" y2="9.5" stroke="currentColor" strokeWidth="1.4" />
      <circle cx="8" cy="11.4" r="0.8" fill="currentColor" />
    </svg>
  ),
  earnings: (
    <svg viewBox="0 0 16 16" fill="none">
      <rect x="2" y="3" width="12" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.3" />
      <line x1="5" y1="1" x2="5" y2="5" stroke="currentColor" strokeWidth="1.4" />
      <line x1="11" y1="1" x2="11" y2="5" stroke="currentColor" strokeWidth="1.4" />
      <circle cx="8" cy="10" r="2" stroke="currentColor" strokeWidth="1.3" />
    </svg>
  ),
  options: (
    <svg viewBox="0 0 16 16" fill="none">
      <polyline points="1,11 5,11 6,5 8,13 10,3 11,9 15,9" stroke="currentColor" strokeWidth="1.4" fill="none" strokeLinejoin="round" />
    </svg>
  ),
  portfolio: (
    <svg viewBox="0 0 16 16" fill="none">
      <path d="M8 2 A 6 6 0 0 1 14 8 H8 Z" fill="currentColor" />
      <path d="M8 2 A 6 6 0 0 0 2 8 H8 Z" stroke="currentColor" strokeWidth="1.3" fill="none" />
      <path d="M8 8 A 6 6 0 0 1 4.5 13.2" stroke="currentColor" strokeWidth="1.3" fill="none" />
    </svg>
  ),
  tape: (
    <svg viewBox="0 0 16 16" fill="none">
      <path d="M2 4 Q 5 1.5, 8 4 T 14 4" stroke="currentColor" strokeWidth="1.3" fill="none" />
      <path d="M2 8 Q 5 5.5, 8 8 T 14 8" stroke="currentColor" strokeWidth="1.3" fill="none" />
      <path d="M2 12 Q 5 9.5, 8 12 T 14 12" stroke="currentColor" strokeWidth="1.3" fill="none" />
    </svg>
  ),
  track: (
    <svg viewBox="0 0 16 16" fill="none">
      <path d="M3 13 L 6 9 L 9 11 L 13 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="13" cy="4" r="1.5" fill="currentColor" />
    </svg>
  ),
  mledge: (
    <svg viewBox="0 0 16 16" fill="none">
      <circle cx="4"  cy="4"  r="1.6" fill="currentColor" />
      <circle cx="12" cy="4"  r="1.6" fill="currentColor" />
      <circle cx="8"  cy="9"  r="1.6" fill="currentColor" />
      <circle cx="4"  cy="13" r="1.6" fill="currentColor" />
      <circle cx="12" cy="13" r="1.6" fill="currentColor" />
      <line x1="4"  y1="4"  x2="8" y2="9" stroke="currentColor" strokeWidth="1" opacity="0.6" />
      <line x1="12" y1="4"  x2="8" y2="9" stroke="currentColor" strokeWidth="1" opacity="0.6" />
      <line x1="8"  y1="9"  x2="4" y2="13" stroke="currentColor" strokeWidth="1" opacity="0.6" />
      <line x1="8"  y1="9"  x2="12" y2="13" stroke="currentColor" strokeWidth="1" opacity="0.6" />
    </svg>
  ),
};

window.LENS_ICONS = LENS_ICONS;
