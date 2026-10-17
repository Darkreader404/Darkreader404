# Interactive profile preview

Open `index.html` directly in a browser. It works with `file://` and needs no build, server, library, or network connection to render. Repository and profile links lead to GitHub when opened.

The BUILD, SIGNAL, and PULSE links adapt the supplied React/styled-components `Radio` component into native HTML anchors. The seven clipping masks and original two-second `glitch` keyframes are preserved. Hover or keyboard focus changes purple (`#882eff`) to lime (`#95ff00`), increases the label size, and reveals the glitch layer. Leaving the link stops the glitch. Reduced-motion preferences retain the lime highlight without the glitch.

The rest of the page reuses `../assets/`: the avatar, responsive hero, project cards, contribution and activity snapshots, and footer. The layout switches to a single column on narrow screens; mobile picture sources preserve readable chart labels.

GitHub sanitizes README HTML and does not run custom hover CSS or React. This interactive preview demonstrates the requested interaction; the GitHub README uses the existing SVG button artwork and native links.
