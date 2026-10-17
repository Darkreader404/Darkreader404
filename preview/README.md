# Y2K glass profile preview

Open `index.html` directly in a browser. It needs no build, dependencies, fonts, server, or network connection to render; profile and project links open GitHub.

The design is a Y2K personal desktop: translucent cyan and icy blue windows, beveled chrome edges, iridescent accents, the existing robot profile avatar, a decorative CD player, and glossy cyan, icy blue, and aqua navigation tabs. It reuses the local assets in `../assets/` and switches to a compact layout with mobile chart artwork on narrow screens.

The BUILD, SIGNAL, and PULSE anchors retain the supplied React/styled-components Radio component’s seven clipping masks and original two-second `glitch` keyframes. Hover or keyboard focus changes each glossy tab to bright aqua and reveals the glitch layer. Leaving the tab stops the animation. Reduced-motion preferences retain the bright aqua highlight with no glitch. All navigation remains native and keyboard accessible.

The media player is a visual motif, not an audio control. Window controls are decorative. Chart images display their snapshot date and real contribution data; the ECG decoration is not a medical measurement.

GitHub READMEs display the matching SVG artwork and links but do not execute custom hover CSS or React. This browser edition provides the full glass and hover experience.
