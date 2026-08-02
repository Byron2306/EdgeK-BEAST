# BEAST Phase 9.1.5 — Unique Hacker Type

## Purpose

Replace the remaining generic desktop typography with a real BEAST type hierarchy.

## Active font system

- **Display:** Orbitron, with Oxanium and Chakra Petch fallbacks
- **Panel hierarchy:** Oxanium and Chakra Petch
- **Navigation and controls:** Rajdhani
- **Terminal, telemetry and logs:** Share Tech Mono
- **Code editor request:** JetBrains Mono / IBM Plex Mono / Share Tech Mono

The full suggested font palette is requested from Google Fonts: Orbitron, Oxanium, Chakra Petch, Rajdhani, Aldrich, Michroma, Teko, Share Tech Mono, IBM Plex Mono, JetBrains Mono, Space Mono and Azeret Mono. No font binaries are bundled in the package. If the renderer is offline, the CSS falls back to installed technical fonts without reverting to named Arial, Times, Impact, Segoe UI or serif families.

## Files

- `css/beast-phase9-1-5-unique-hacker-fonts.css`
- `js/beast-phase9-1-5-font-loader.js`
- updated HTML font links and phase labels
- cleaned active font declarations in token, hi-def signal and Phase 9.1.4 CSS

## Remaining roadmap

- Phase 10: production integration and legacy purge
- Phase 11: responsive, accessibility and performance acceptance
- Phase 12: release candidate
