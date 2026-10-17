# Profile design notes

The profile is built from Markdown links and self-contained SVG images. It needs no React build, JavaScript, npm packages, custom fonts, or external stats-card service. SVG gradients, translucent surfaces, borders, and glow simulate glass within GitHub's README renderer. The native GitHub sidebar, pinned repositories, and contribution calendar are controlled by GitHub; the themed panels appear inside the README.

## Supplied component adaptations

- **Contribution loader:** 18 candles, 2.6-second animation, and 65-millisecond stagger, adapted to show actual contribution counts. Each candle covers a trailing seven-day window; its body is the first/last daily count and its wick is the minimum/maximum. Flat zero-count candles remain visible. The original supplied candle snippet included the credit `IG: @bilalbstn7`.
- **Heart-rate card:** pink rounded bars, endpoint dots, a daily-average guide, and recent readings become a seven-day contribution card. Counts measure GitHub contributions; the ECG is decorative.
- **Cyber radio buttons:** clipped corners, r1/r2/r3 labels, and brief glitch accents become three actual README navigation links. GitHub cannot execute the supplied React components or radio-button behavior inside a README.

All animated assets have a visible static baseline and respect `prefers-reduced-motion`. The hero and telemetry panels have separate narrow-screen compositions selected using `<picture>`. Project cards wrap into a single column on narrow screens. README alt text and ordinary text links preserve the content if images are unavailable.

## Content and data

Identity and pronouns come from the supplied screenshot. Project descriptions and DRONEX's OpenSCAD/Python languages were checked against the public repositories. Medical and market visuals are design themes, with no invented professional credentials, medical readings, or trading returns. Follower, star, and repository counts are intentionally not frozen into the artwork.

`assets/profile-data.json` contains a dated, public contribution snapshot. Scheduled refreshes always use GitHub's anonymous public calendar, so totals can differ from the account owner's private view. The time window is 365 contiguous UTC dates, ending on the snapshot date; today's count can still change. Candles cover 18 complete trailing seven-day windows. The activity chart uses the final seven dates from the same snapshot.

## Refreshing

```sh
python3 scripts/update_profile.py --public
```

The workflow in `.github/workflows/profile-telemetry.yml` refreshes the panels daily and can also be run manually from the Actions tab. It starts after these files are pushed to the repository's default branch and requires Actions and workflow write access to be enabled. Protected branches may require adjusting the commit workflow. Fetch or validation failures preserve the last valid snapshot and display its capture time.

For an offline render from the saved snapshot:

```sh
python3 scripts/update_profile.py --from-json assets/profile-data.json --output-dir /tmp/profile-preview
```

The script also supports optional authenticated GraphQL locally. Those counts may include private activity depending on token permissions and profile settings, so use `--public` to match the visitor-facing profile. No token is needed for the scheduled data fetch; the workflow uses its standard repository token only to save the generated files.

Edit the static hero, project cards, buttons, and footer directly in `assets/`. Edit telemetry layout in `scripts/update_profile.py`, then rerender it. Publish the README **with all referenced assets**, the refresh script, and its workflow. GitHub may briefly cache older images.
