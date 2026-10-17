#!/usr/bin/env python3
"""Refresh self-contained SVG profile panels from one GitHub calendar snapshot.

Only Python's standard library is required. With GITHUB_TOKEN/GH_TOKEN (or a local
`gh auth token`), use GitHub GraphQL. Without credentials, parse GitHub's public
contribution calendar, including exact tooltip counts rather than color levels.
No credentials are stored or printed. An authenticated calendar can include
private counts permitted by the token/user settings; the artwork calls these
GitHub contributions and does not imply commits, trades, or medical readings.

The year panel contains exactly 365 UTC calendar dates ending today. Candles use
18 complete trailing seven-day windows (126 dates, with no padded partial week):
body = first/last daily count; wick = min/max daily count. A flat candle is a real
zero/doji, not missing data. The activity panel uses the last seven dates from
that same snapshot, with a seven-day mean. Today can still accrue contributions.
The pulse trace is explicitly decorative. Desktop and mobile SVGs use the same
snapshot, with independent layouts rather than scaling a desktop composition.

All input is validated and every output rendered before any asset is replaced.
Network, authentication, or parsing failures leave existing assets untouched.
Use --from-json assets/profile-data.json --output-dir /tmp/profile-preview for a
deterministic offline render. Data origin is preserved in that mode.
"""

import argparse
import datetime as dt
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent.parent
UTC = dt.timezone.utc
COLORS = {"cyan": "#8cf4ff", "mint": "#bdfff7", "pink": "#a5fff1", "violet": "#5fe3ff"}


class CalendarParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.dates = {}
        self.counts = {}
        self.tip = None
        self.tip_text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "td" and "data-date" in attrs:
            self.dates[attrs["id"]] = attrs["data-date"]
        if tag == "tool-tip":
            self.tip = attrs.get("for")
            self.tip_text = []

    def handle_data(self, text):
        if self.tip:
            self.tip_text.append(text)

    def handle_endtag(self, tag):
        if tag == "tool-tip" and self.tip:
            match = re.match(r"\s*(No|[\d,]+) contributions? on ", "".join(self.tip_text))
            if match:
                self.counts[self.tip] = 0 if match[1] == "No" else int(match[1].replace(",", ""))
            self.tip = None
            self.tip_text = []


def request(url, data=None, token=None):
    headers = {"User-Agent": "Darkreader404-profile-telemetry", "Accept": "application/json" if data else "text/html"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=35) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise ValueError("GitHub returned HTTP %s; existing assets were kept" % exc.code) from None
    except urllib.error.URLError as exc:
        raise ValueError("GitHub request failed (%s); existing assets were kept" % exc.reason) from None


def get_token():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token and shutil.which("gh"):
        result = subprocess.run(["gh", "auth", "token", "--hostname", "github.com"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            token = result.stdout.strip()
    return token


def fetch_snapshot(user, public=False):
    now = dt.datetime.now(UTC).replace(microsecond=0)
    end = now.date()
    start = end - dt.timedelta(days=364)
    token = None if public else get_token()
    if token:
        query = """query($login:String!,$from:DateTime!,$to:DateTime!) {
          user(login:$login) { contributionsCollection(from:$from,to:$to) {
            restrictedContributionsCount
            contributionCalendar { totalContributions weeks {
              contributionDays { date contributionCount }
            } }
          } }
        }"""
        payload = json.dumps({"query": query, "variables": {"login": user, "from": start.isoformat() + "T00:00:00Z", "to": now.isoformat().replace("+00:00", "Z")}}).encode()
        response = json.loads(request("https://api.github.com/graphql", payload, token))
        if response.get("errors") or not response.get("data", {}).get("user"):
            raise ValueError("GitHub GraphQL did not return a calendar; existing assets were kept")
        collection = response["data"]["user"]["contributionsCollection"]
        calendar = collection["contributionCalendar"]
        days = [day for week in calendar["weeks"] for day in week["contributionDays"]]
        source = "GitHub GraphQL calendar"
        restricted = collection["restrictedContributionsCount"]
    else:
        parser = CalendarParser()
        parser.feed(request("https://github.com/users/%s/contributions" % user))
        days = [{"date": date, "contributionCount": parser.counts[key]} for key, date in parser.dates.items() if key in parser.counts]
        source = "Public GitHub calendar"
        restricted = None
    days = sorted((day for day in days if start.isoformat() <= day["date"] <= end.isoformat()), key=lambda day: day["date"])
    snapshot = {"user": user, "source": source, "source_url": "https://github.com/%s?tab=overview" % user,
                "fetched_at": now.isoformat().replace("+00:00", "Z"), "start_date": start.isoformat(), "end_date": end.isoformat(),
                "total_contributions": sum(day["contributionCount"] for day in days), "restricted_contributions": restricted, "days": days}
    validate_snapshot(snapshot)
    if token and snapshot["total_contributions"] != calendar["totalContributions"]:
        raise ValueError("GitHub calendar total did not match daily counts; existing assets were kept")
    return snapshot


def validate_snapshot(data):
    start = dt.date.fromisoformat(data["start_date"])
    end = dt.date.fromisoformat(data["end_date"])
    dt.datetime.fromisoformat(data["fetched_at"].replace("Z", "+00:00"))
    expected = [(start + dt.timedelta(days=i)).isoformat() for i in range(365)]
    if end != start + dt.timedelta(days=364) or [day["date"] for day in data["days"]] != expected:
        raise ValueError("Calendar must contain exactly 365 contiguous dates; existing assets were kept")
    counts = [day["contributionCount"] for day in data["days"]]
    if any(type(count) is not int or count < 0 for count in counts) or sum(counts) != data["total_contributions"]:
        raise ValueError("Invalid daily counts or calendar total; existing assets were kept")
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", data["user"]):
        raise ValueError("Invalid GitHub username")


def esc(value):
    return html.escape(str(value), quote=True)


def text(x, y, value, size=13, color="#b3d2df", weight=400, mono=False, **attrs):
    extra = " ".join('%s="%s"' % (key.replace("_", "-"), esc(value)) for key, value in attrs.items())
    family = "'SFMono-Regular',Consolas,monospace" if mono else "Arial,Helvetica,sans-serif"
    return '<text x="%s" y="%s" fill="%s" font-size="%s" font-weight="%s" font-family="%s" %s>%s</text>' % (x, y, color, size, weight, family, extra, esc(value))


def panel(x, y, width, height):
    return '<rect x="%s" y="%s" width="%s" height="%s" rx="18" fill="#0c191f" fill-opacity=".55" stroke="#e3fbff" stroke-opacity=".13"/>' % (x, y, width, height)


def sparkle(x, y, radius=10, color="#e3fbff"):
    return '<path d="M%s %sQ%s %s %s %sQ%s %s %s %sQ%s %s %s %sQ%s %s %s %sZ" fill="%s"/>' % (x, y-radius, x, y, x+radius, y, x, y, x, y+radius, x, y, x-radius, y, x, y, x, y-radius, color)


def frame(title, description, accent, width=1200, height=340):
    mobile = width == 600
    return ['<svg xmlns="http://www.w3.org/2000/svg" width="%s" height="%s" viewBox="0 0 %s %s" role="img" aria-labelledby="title desc">' % (width, height, width, height),
            '<title id="title">%s</title><desc id="desc">%s</desc>' % (esc(title), esc(description)),
            '<defs><linearGradient id="glass" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#2b5364" stop-opacity=".83"/><stop offset=".47" stop-color="#123446" stop-opacity=".78"/><stop offset="1" stop-color="#0c191f" stop-opacity=".96"/></linearGradient><linearGradient id="chrome" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#e3fbff" stop-opacity=".8"/><stop offset=".28" stop-color="#8cf4ff" stop-opacity=".22"/><stop offset=".57" stop-color="#5fe3ff" stop-opacity=".6"/><stop offset="1" stop-color="#a5fff1" stop-opacity=".3"/></linearGradient><linearGradient id="titlebar" x2="0" y2="1"><stop stop-color="#e3fbff" stop-opacity=".18"/><stop offset=".48" stop-color="#e3fbff" stop-opacity=".05"/><stop offset=".51" stop-color="#5fe3ff" stop-opacity=".03"/><stop offset="1" stop-color="#5fe3ff" stop-opacity=".12"/></linearGradient><radialGradient id="aura"><stop stop-color="%s" stop-opacity=".23"/><stop offset="1" stop-color="%s" stop-opacity="0"/></radialGradient><radialGradient id="pink-aura"><stop stop-color="#a5fff1" stop-opacity=".16"/><stop offset="1" stop-color="#a5fff1" stop-opacity="0"/></radialGradient><linearGradient id="pink" x2="0" y2="1"><stop stop-color="#e4fefe"/><stop offset=".32" stop-color="#a5fff1"/><stop offset="1" stop-color="#5fe3ff" stop-opacity=".45"/></linearGradient><clipPath id="frame-clip"><rect x="1" y="1" width="%s" height="%s" rx="28"/></clipPath></defs>' % (accent, accent, width - 2, height - 2),
            '<style>.candle{animation:candle-glow 2.6s ease-in-out infinite}.pulse{stroke-dasharray:420;animation:pulse-flow 5s linear infinite}@keyframes candle-glow{0%,100%{opacity:.65}40%{opacity:1}}@keyframes pulse-flow{from{stroke-dashoffset:840}to{stroke-dashoffset:0}}@media(prefers-reduced-motion:reduce){.candle,.pulse{animation:none}}</style>',
            '<rect x="1" y="1" width="%s" height="%s" rx="28" fill="#041019"/>' % (width - 2, height - 2),
            '<g clip-path="url(#frame-clip)"><ellipse cx="%s" cy="40" rx="360" ry="260" fill="url(#aura)"/><ellipse cx="100" cy="%s" rx="320" ry="230" fill="url(#pink-aura)"/></g>' % (width - 100, height),
            '<rect x="1.5" y="1.5" width="%s" height="%s" rx="27.5" fill="url(#glass)" stroke="url(#chrome)" stroke-width="1.5"/>' % (width - 3, height - 3),
            '<rect x="13" y="13" width="%s" height="42" rx="16" fill="url(#titlebar)" stroke="#e3fbff" stroke-opacity=".16"/>' % (width - 26),
            '<path d="M32 15H%s" stroke="#fff" stroke-opacity=".22"/>' % (width - 32),
            '<g fill="none" stroke="#e3fbff" stroke-opacity=".6" stroke-width="1.2"><rect x="%s" y="25" width="17" height="17" rx="5"/><rect x="%s" y="25" width="17" height="17" rx="5"/><path d="M%s 33h7m13-4 7 8m-7 0 7-8"/></g>' % (width - 77, width - 51, width - 72),
            '<ellipse cx="%s" cy="77" rx="43" ry="12" transform="rotate(-17 %s 77)" fill="none" stroke="#5fe3ff" stroke-opacity=".22"/>' % (width - 75, width - 75),
            sparkle(width - (122 if mobile else 150), 75, 7, "#8cf4ff")]


def short_date(value):
    return dt.date.fromisoformat(value).strftime("%d %b %Y").upper()


def footer(data):
    stamp = dt.datetime.fromisoformat(data["fetched_at"].replace("Z", "+00:00")).strftime("%d %b %Y %H:%M UTC")
    return text(44, 319, "%s · captured %s · current day may still change" % (data["source"], stamp), 10)


def contributions_label(data):
    return "PUBLIC GITHUB CONTRIBUTIONS" if data["source"] == "Public GitHub calendar" else "GITHUB CONTRIBUTIONS"


def mobile_footer(data):
    stamp = dt.datetime.fromisoformat(data["fetched_at"].replace("Z", "+00:00")).strftime("%d %b %Y %H:%M UTC")
    return [text(28, 480, data["source"], 13), text(28, 502, "%s · current day may still change" % stamp, 13)]


def contributions_svg(data):
    counts = [day["contributionCount"] for day in data["days"]]
    total, active, peak = sum(counts), sum(count > 0 for count in counts), max(counts)
    parts = frame("Darkreader404 · Contribution market", "365 days of actual GitHub contributions. Total %s. Weekly candles show daily first/last and low/high counts; the heatmap shows each actual day." % total, COLORS["mint"])
    parts += [panel(28, 92, 368, 120), panel(412, 92, 752, 120), panel(28, 221, 1136, 85), text(44, 38, "CONTRIBUTION.exe / 02", 11, COLORS["mint"], 600, True, letter_spacing="1.8"),
              text(44, 78, "Build a little. Compound it.", 28, "#effaff", 700, font_style="italic"),
              text(1086, 38, "GROWTH / SIGNAL / REPEAT", 10, "#b3d2df", 400, True, text_anchor="end"),
              text(44, 140, total, 54, "#effaff", 700), text(44, 163, contributions_label(data) + " / 365 DAYS", 11, "#b3d2df", 500, True),
              text(44, 190, "%s active days   /   %s peak in one day" % (active, peak), 12),
              text(429, 107, "CANDLE.view / 18 × 7 DAYS", 10, COLORS["mint"], 600, True),
              text(1155, 107, "body: first / last day · wick: min / max", 10, "#b3d2df", text_anchor="end")]
    groups = [data["days"][-126:][i:i + 7] for i in range(0, 126, 7)]
    scale = 67 / max(1, max(day["contributionCount"] for group in groups for day in group))
    base = 189
    parts.append('<path d="M429 189H1156M429 151H1156" fill="none" stroke="#ffffff" stroke-opacity=".08" stroke-dasharray="3 6"/>')
    for index, group in enumerate(groups):
        values = [day["contributionCount"] for day in group]
        first, last, low, high = values[0], values[-1], min(values), max(values)
        x = 449 + index * 40.2
        color = COLORS["mint"] if last >= first else COLORS["pink"]
        top, height = base - max(first, last) * scale, abs(last - first) * scale
        # A minimum two-pixel doji keeps real zero candles visible, without a fake value.
        title = "%s to %s: first %s, last %s, low %s, high %s contributions/day" % (group[0]["date"], group[-1]["date"], first, last, low, high)
        parts.append('<g class="candle" style="animation-delay:%.3fs"><title>%s</title><path d="M%.1f %.1fV%.1f" stroke="%s" stroke-width="1.5"/><rect x="%.1f" y="%.1f" width="10" height="%.1f" rx="1" fill="%s"/></g>' % (index * .065, esc(title), x, base - high * scale, base - low * scale, color, x - 5, top - (1 if height == 0 else 0), max(2, height), color))
    parts += [text(429, 207, short_date(groups[0][0]["date"]), 9, "#b3d2df", mono=True), text(1156, 207, short_date(groups[-1][-1]["date"]), 9, "#b3d2df", mono=True, text_anchor="end"),
              '<path d="M44 221H1156" stroke="#ffffff" stroke-opacity=".1"/>', text(44, 247, "YEAR.archive / 365", 10, COLORS["cyan"], 600, True),
              text(44, 269, short_date(data["start_date"]), 10, mono=True), text(44, 286, short_date(data["end_date"]), 10, mono=True)]
    first_date = dt.date.fromisoformat(data["start_date"])
    offset = (first_date.weekday() + 1) % 7
    palette = ["#234351", "#3f8492", "#65aebd", "#98c9d3", COLORS["mint"]]
    for index, day in enumerate(data["days"]):
        count = day["contributionCount"]
        cell = offset + index
        x, y = 245 + (cell // 7) * 17.2, 232 + (cell % 7) * 10
        level = 0 if count == 0 else max(1, min(4, (count * 4 + max(1, peak) - 1) // max(1, peak)))
        parts.append('<rect x="%.1f" y="%s" width="12" height="8" rx="2" fill="%s"><title>%s: %s contribution%s</title></rect>' % (x, y, palette[level], day["date"], count, "" if count == 1 else "s"))
    parts += [footer(data), '</svg>']
    return "\n".join(parts) + "\n"


def activity_svg(data):
    days = data["days"][-7:]
    counts = [day["contributionCount"] for day in days]
    total, peak, average = sum(counts), max(counts), sum(counts) / 7
    parts = frame("Darkreader404 · Activity vitals", "Actual contributions for %s through %s: %s total, %.1f daily average. The pulse trace is a decorative medical design motif, not a medical measurement." % (days[0]["date"], days[-1]["date"], total, average), COLORS["pink"])
    parts += [panel(28, 120, 694, 178), panel(754, 92, 410, 206), text(44, 38, "PULSE.monitor / 03", 11, COLORS["pink"], 600, True, letter_spacing="1.8"),
              text(44, 78, "Every contribution has a pulse.", 28, "#effaff", 700, font_style="italic"),
              text(44, 105, "%s — %s · 7-day contribution rhythm" % (short_date(days[0]["date"]), short_date(days[-1]["date"])), 12),
              text(1086, 38, "DEVELOPER SIGNAL / 7D", 10, "#b3d2df", mono=True, text_anchor="end"),
              '<path d="M736 92V291" stroke="#ffffff" stroke-opacity=".12"/>']
    scale = 90 / max(1, peak)
    base = 263
    avg_y = base - average * scale
    parts += ['<path d="M68 263H686M68 173H686" stroke="#ffffff" stroke-opacity=".08"/>',
              '<path d="M68 %.1fH686" stroke="#a5fff1" stroke-opacity=".4" stroke-dasharray="4 5"/>' % avg_y,
              text(686, 140, "DAILY AVG  %.1f" % average, 10, COLORS["pink"], 600, True, text_anchor="end")]
    for index, day in enumerate(days):
        count = day["contributionCount"]
        x, height = 104 + index * 89, count * scale
        title = "%s: %s contribution%s" % (day["date"], count, "" if count == 1 else "s")
        parts.append('<g><title>%s</title><rect x="%s" y="%.1f" width="24" height="%.1f" rx="%s" fill="%s"/>%s</g>' % (esc(title), x - 12, base - max(3, height), max(3, height), 10 if height > 20 else 1.5, "url(#pink)" if count else "#3b738b", text(x, base - max(3, height) - 10, count, 13, "#effaff" if count else "#b3d2df", 600, text_anchor="middle")))
        if count:
            parts.append('<circle cx="%s" cy="%.1f" r="4" fill="#effaff" stroke="#a5fff1" stroke-width="2"/>' % (x, base - height))
        parts.append(text(x, 285, dt.date.fromisoformat(day["date"]).strftime("%a").upper(), 10, mono=True, text_anchor="middle"))
    parts += [text(779, 113, contributions_label(data) + " / 7D", 10, COLORS["pink"], 600, True), text(779, 157, total, 42, "#effaff", 700),
              text(900, 156, "contributions", 14), text(1156, 153, "%s / DAY PEAK" % peak, 10, COLORS["pink"], 600, True, text_anchor="end"),
              '<path d="M779 198H820L830 189L840 207L853 173L867 222L883 198H919L932 189L944 207L957 184L971 211L984 198H1156" stroke="#a5fff1" stroke-opacity=".2" stroke-width="2" fill="none"/>',
              '<path class="pulse" d="M779 198H820L830 189L840 207L853 173L867 222L883 198H919L932 189L944 207L957 184L971 211L984 198H1156" stroke="#a5fff1" stroke-width="2" fill="none"/>',
              text(779, 241, "HEARTBEAT.skin / DECORATIVE", 9, "#b3d2df", mono=True),
              '<path d="M779 256H1156" stroke="#ffffff" stroke-opacity=".1"/>',
              text(779, 279, short_date(days[-1]["date"]), 10, mono=True), text(1156, 279, "%s CONTRIBUTIONS" % counts[-1], 11, "#effaff", 600, True, text_anchor="end"),
              footer(data), '</svg>']
    return "\n".join(parts) + "\n"


def contributions_mobile_svg(data):
    counts = [day["contributionCount"] for day in data["days"]]
    total, active, peak = sum(counts), sum(count > 0 for count in counts), max(counts)
    parts = frame("Darkreader404 · Contribution market", "365 days of actual GitHub contributions. Total %s. Eighteen complete seven-day candles show daily first/last and low/high counts; the heatmap shows each actual day." % total, COLORS["mint"], 600, 520)
    label_x = max(125, 28 + len(str(total)) * 30 + 18)
    parts += [panel(16, 82, 568, 90), panel(16, 178, 568, 154), panel(16, 344, 568, 122), text(28, 38, "CONTRIBUTION.exe / 02", 13, COLORS["mint"], 600, True, letter_spacing="1.2"),
              text(28, 68, "Build a little. Compound it.", 26, "#effaff", 700, font_style="italic"),
              text(28, 134, total, 50, "#effaff", 700),
              text(label_x, 111, contributions_label(data), 13, "#b3d2df", 500, True),
              text(label_x, 134, "ROLLING 365 DAYS", 13, "#b3d2df", 400, True),
              text(28, 158, "%s active days / %s peak in one day" % (active, peak), 13),
              text(28, 193, "CANDLE.view / 18 × 7 DAYS", 13, COLORS["mint"], 600, True),
              text(28, 214, "Body: first / last day · wick: min / max", 13)]
    groups = [data["days"][-126:][i:i + 7] for i in range(0, 126, 7)]
    scale = 60 / max(1, max(day["contributionCount"] for group in groups for day in group))
    base = 294
    parts.append('<path d="M28 294H572M28 254H572" fill="none" stroke="#ffffff" stroke-opacity=".08" stroke-dasharray="3 6"/>')
    for index, group in enumerate(groups):
        values = [day["contributionCount"] for day in group]
        first, last, low, high = values[0], values[-1], min(values), max(values)
        x = 42 + index * 30.25
        color = COLORS["mint"] if last >= first else COLORS["pink"]
        top, height = base - max(first, last) * scale, abs(last - first) * scale
        title = "%s to %s: first %s, last %s, low %s, high %s contributions/day" % (group[0]["date"], group[-1]["date"], first, last, low, high)
        parts.append('<g class="candle" style="animation-delay:%.3fs"><title>%s</title><path d="M%.1f %.1fV%.1f" stroke="%s" stroke-width="1.5"/><rect x="%.1f" y="%.1f" width="8" height="%.1f" rx="1" fill="%s"/></g>' % (index * .065, esc(title), x, base - high * scale, base - low * scale, color, x - 4, top - (1 if height == 0 else 0), max(2, height), color))
    parts += [text(28, 316, short_date(groups[0][0]["date"]), 13, mono=True), text(572, 316, short_date(groups[-1][-1]["date"]), 13, mono=True, text_anchor="end"),
              '<path d="M28 335H572" stroke="#ffffff" stroke-opacity=".1"/>',
              text(28, 358, "YEAR.archive / 365", 13, COLORS["cyan"], 600, True)]
    first_date = dt.date.fromisoformat(data["start_date"])
    offset = (first_date.weekday() + 1) % 7
    palette = ["#234351", "#3f8492", "#65aebd", "#98c9d3", COLORS["mint"]]
    for index, day in enumerate(data["days"]):
        count = day["contributionCount"]
        cell = offset + index
        x, y = 38 + (cell // 7) * 10, 371 + (cell % 7) * 10
        level = 0 if count == 0 else max(1, min(4, (count * 4 + max(1, peak) - 1) // max(1, peak)))
        parts.append('<rect x="%s" y="%s" width="6" height="6" rx="1.5" fill="%s"><title>%s: %s contribution%s</title></rect>' % (x, y, palette[level], day["date"], count, "" if count == 1 else "s"))
    parts += [text(28, 457, "%s — %s" % (short_date(data["start_date"]), short_date(data["end_date"])), 13), *mobile_footer(data), '</svg>']
    return "\n".join(parts) + "\n"


def activity_mobile_svg(data):
    days = data["days"][-7:]
    counts = [day["contributionCount"] for day in days]
    total, peak, average = sum(counts), max(counts), sum(counts) / 7
    parts = frame("Darkreader404 · Activity vitals", "Actual contributions for %s through %s: %s total, %.1f daily average. The pulse trace is a decorative medical design motif, not a medical measurement." % (days[0]["date"], days[-1]["date"], total, average), COLORS["pink"], 600, 520)
    unit_x = max(100, 28 + len(str(total)) * 27 + 18)
    parts += [panel(16, 107, 568, 69), panel(16, 183, 568, 183), panel(16, 375, 568, 91), text(28, 38, "PULSE.monitor / 03", 13, COLORS["pink"], 600, True, letter_spacing="1.2"),
              text(28, 68, "Every contribution has a pulse.", 26, "#effaff", 700, font_style="italic"),
              text(28, 94, "%s — %s" % (short_date(days[0]["date"]), short_date(days[-1]["date"])), 13),
              text(28, 123, contributions_label(data) + " / 7D", 13, COLORS["pink"], 600, True),
              text(28, 166, total, 42, "#effaff", 700), text(unit_x, 160, "contributions", 15),
              text(572, 138, "%.1f DAILY AVG" % average, 13, COLORS["pink"], 600, True, text_anchor="end"),
              text(572, 160, "%s / DAY PEAK" % peak, 13, "#b3d2df", 400, True, text_anchor="end"),
              text(28, 197, "7-DAY CONTRIBUTION RHYTHM", 13, "#b3d2df", 400, True)]
    scale = 104 / max(1, peak)
    base = 332
    avg_y = base - average * scale
    parts += ['<path d="M28 332H572M28 228H572" stroke="#ffffff" stroke-opacity=".08"/>',
              '<path d="M28 %.1fH572" stroke="#a5fff1" stroke-opacity=".4" stroke-dasharray="4 5"/>' % avg_y]
    for index, day in enumerate(days):
        count = day["contributionCount"]
        x, height = 58 + index * 80, count * scale
        title = "%s: %s contribution%s" % (day["date"], count, "" if count == 1 else "s")
        parts.append('<g><title>%s</title><rect x="%s" y="%.1f" width="22" height="%.1f" rx="%s" fill="%s"/>%s</g>' % (esc(title), x - 11, base - max(3, height), max(3, height), 10 if height > 20 else 1.5, "url(#pink)" if count else "#3b738b", text(x, base - max(3, height) - 10, count, 13, "#effaff" if count else "#b3d2df", 600, text_anchor="middle")))
        if count:
            parts.append('<circle cx="%s" cy="%.1f" r="4" fill="#effaff" stroke="#a5fff1" stroke-width="2"/>' % (x, base - height))
        parts.append(text(x, 354, dt.date.fromisoformat(day["date"]).strftime("%a").upper(), 13, mono=True, text_anchor="middle"))
    pulse = "M28 412H114L125 402L136 423L151 385L168 439L185 412H277L292 402L305 425L321 393L339 428L357 412H572"
    parts += ['<path d="M28 370H572" stroke="#ffffff" stroke-opacity=".1"/>',
              '<path d="%s" stroke="#a5fff1" stroke-opacity=".2" stroke-width="2" fill="none"/>' % pulse,
              '<path class="pulse" d="%s" stroke="#a5fff1" stroke-width="2" fill="none"/>' % pulse,
              text(28, 457, "Pulse trace / decorative medical motif", 13), *mobile_footer(data), '</svg>']
    return "\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--user", default="Darkreader404")
    parser.add_argument("--public", action="store_true", help="Use GitHub's unauthenticated public calendar even if a token is available")
    parser.add_argument("--from-json", type=Path, help="Render a previously saved snapshot without network access")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "assets")
    args = parser.parse_args()
    try:
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", args.user):
            raise ValueError("Invalid GitHub username")
        data = json.loads(args.from_json.read_text()) if args.from_json else fetch_snapshot(args.user, args.public)
        validate_snapshot(data)
        outputs = {"contributions.svg": contributions_svg(data), "activity.svg": activity_svg(data),
                   "contributions-mobile.svg": contributions_mobile_svg(data), "activity-mobile.svg": activity_mobile_svg(data),
                   "profile-data.json": json.dumps(data, indent=2) + "\n"}
        for name, content in outputs.items():
            if name.endswith(".svg"):
                ET.fromstring(content)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=args.output_dir, prefix=".profile-") as temp:
            for name, content in outputs.items():
                Path(temp, name).write_text(content, encoding="utf-8")
            for name in outputs:
                os.replace(Path(temp, name), args.output_dir / name)
        print("Updated %s: %s contributions across 365 dates through %s (%s)." % (data["user"], data["total_contributions"], data["end_date"], data["source"]))
        return 0
    except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired, ET.ParseError) as exc:
        print("Profile refresh failed: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
