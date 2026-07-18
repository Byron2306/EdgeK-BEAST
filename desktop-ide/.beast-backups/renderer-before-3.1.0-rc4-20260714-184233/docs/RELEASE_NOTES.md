# BEAST IDE 3.1.0-rc4 · BLACKGLASS Visual Stabilization

Released: 2026-07-14

RC4 is a corrective release candidate produced after visual inspection exposed clipping, uneven page geometry, weak typography hierarchy and fragmented animation ownership in RC3.

## Stabilized in RC4

- Rebuilt the production stylesheet as one authoritative property-merged owner rather than a stack of historical phase overrides.
- Standardized page headers, title/action safe zones, card spacing, command-dock height and right-rail wrapping.
- Corrected SourcePlan, Review, Settings, Tooling and compact-viewport layout failures.
- Preserved the requested hacker typography families: Orbitron, Oxanium, Chakra Petch, Aldrich, Rajdhani, Share Tech Mono, JetBrains Mono, IBM Plex Mono, Azeret Mono and Space Mono.
- Raised formerly 7–9px route text to a readable operational floor.
- Replaced duplicate atmosphere and visual controllers with one `beast-visual-runtime.js` animation owner.
- Restored Matrix rain, foreground rain, square grid, perspective grid, header current and card heartbeat effects with adaptive performance tiers.
- Added route/profile evidence for all 22 routes at five viewport profiles, totaling 110 automated visual scenarios.

## Acceptance result

Automated structural and visual geometry checks pass for 110/110 scenarios. Intentional overflow remains only inside owned mission-stage and radial-memory visual components. Live Electron preload, Monaco, gateway mutations and streaming operations remain pending operator acceptance.
