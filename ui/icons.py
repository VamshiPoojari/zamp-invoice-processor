"""
Inline SVG icons (no emoji anywhere in the UI).
Status colours follow a fixed status palette and are always paired with a label,
so meaning never depends on colour alone.
"""

GOOD = "#0ca30c"      # approve / pass
WARNING = "#fab219"   # hold / warning
CRITICAL = "#d03b3b"  # reject / fail
NEUTRAL = "#9ca3af"
ACCENT = "#2f5bea"

# glyph paths drawn inside a 24x24 filled circle
_GLYPH = {
    "check": '<path d="m7.5 12.5 3 3 6-6.5"/>',
    "x": '<path d="m9 9 6 6"/><path d="m15 9-6 6"/>',
    "pause": '<path d="M10 8.5v7"/><path d="M14 8.5v7"/>',
    "bang": '<path d="M12 7v6"/><path d="M12 16.6v.1"/>',
    "minus": '<path d="M8 12h8"/>',
}

# status -> (fill, glyph, glyph colour)
_STATUS = {
    "pass": (GOOD, "check", "#fff"),
    "APPROVE": (GOOD, "check", "#fff"),
    "warn": (WARNING, "bang", "#3d2c00"),
    "HOLD": (WARNING, "pause", "#3d2c00"),
    "fail": (CRITICAL, "x", "#fff"),
    "REJECT": (CRITICAL, "x", "#fff"),
    "skipped": ("#e5e7eb", "minus", "#6b7280"),
}


def status_icon(status, size=20):
    """Filled circular badge for pass / warn / fail / APPROVE / HOLD / REJECT, plus
    pending (dashed ring) and running (spinner)."""
    s = f'width="{size}" height="{size}" viewBox="0 0 24 24" aria-hidden="true"'
    if status == "pending":
        return (f'<svg {s} fill="none" stroke="{NEUTRAL}" stroke-width="2">'
                '<circle cx="12" cy="12" r="9" stroke-dasharray="3 3"/></svg>')
    if status == "running":
        return (f'<svg {s} class="spin" fill="none" stroke="{ACCENT}" stroke-width="2.5" '
                'stroke-linecap="round"><circle cx="12" cy="12" r="9" stroke="#dbe4ff"/>'
                '<path d="M21 12a9 9 0 0 0-9-9"/></svg>')
    fill, glyph, ink = _STATUS.get(status, _STATUS["skipped"])
    return (f'<svg {s}><circle cx="12" cy="12" r="11" fill="{fill}"/>'
            f'<g fill="none" stroke="{ink}" stroke-width="2.4" stroke-linecap="round" '
            f'stroke-linejoin="round">{_GLYPH[glyph]}</g></svg>')


# outline icons (lucide-style), 24x24, stroke = currentColor
_LINE = {
    "logo": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/>'
            '<path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M8 13h8"/><path d="M8 17h5"/>',
    "shield": '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 '
              '1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>'
              '<path d="M12 8v4"/><path d="M12 16h.01"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M20 21a8 8 0 0 0-16 0"/>',
    "arrow": '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "cpu": '<rect x="5" y="5" width="14" height="14" rx="2"/><path d="M9 9h6v6H9z"/>'
           '<path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
    "dollar": '<path d="M12 2v20"/><path d="M17 6H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
    "inbox": '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 '
             '2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
    "zap": '<path d="M13 2 3 14h9l-1 8 10-12h-9z"/>',
}


def line_icon(name, size=16, color="currentColor"):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" '
            f'style="vertical-align:-3px">{_LINE[name]}</svg>')
