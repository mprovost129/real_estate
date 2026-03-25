from django import template

register = template.Library()

TYPE_COLORS = {
    "lead":             ("var(--color-info-bg)",    "var(--color-info)",    "var(--color-info-border)"),
    "prospect":         ("#eef2ff",                  "#4f46e5",              "#c7d2fe"),
    "active_buyer":     ("var(--color-success-bg)",  "var(--color-success)", "var(--color-success-border)"),
    "active_seller":    ("#f0fdfa",                  "#0d9488",              "#99f6e4"),
    "under_contract":   ("var(--color-warning-bg)",  "var(--color-warning)", "var(--color-warning-border)"),
    "past_client":      ("#f8fafc",                  "#475569",              "#e2e8f0"),
    "sphere":           ("#faf5ff",                  "#7c3aed",              "#ddd6fe"),
    "referral_partner": ("#fffbeb",                  "#b45309",              "#fde68a"),
    "vendor":           ("#f8fafc",                  "#64748b",              "#e2e8f0"),
    "investor":         ("#fff7ed",                  "#c2410c",              "#fed7aa"),
    "renter":           ("#f0f9ff",                  "#0369a1",              "#bae6fd"),
    "landlord":         ("#fdf4ff",                  "#a21caf",              "#f0abfc"),
    "other":            ("var(--bg-subtle)",          "var(--text-muted)",    "var(--border-base)"),
}

PRIORITY_COLORS = {
    "low":    "#94a3b8",
    "normal": "#3b82f6",
    "high":   "#f59e0b",
    "urgent": "#ef4444",
}


@register.filter
def type_badge_style(contact_type):
    bg, color, border = TYPE_COLORS.get(contact_type, TYPE_COLORS["other"])
    return f"background:{bg};color:{color};border:1px solid {border};"


@register.filter
def priority_color(priority):
    return PRIORITY_COLORS.get(priority, "#94a3b8")


@register.simple_tag
def note_type_icon(note_type):
    icons = {
        "call":       "bi-telephone-fill",
        "text":       "bi-chat-fill",
        "email":      "bi-envelope-fill",
        "meeting":    "bi-calendar-event-fill",
        "showing":    "bi-house-fill",
        "open_house": "bi-door-open-fill",
        "task":       "bi-check2-square",
        "system":     "bi-gear-fill",
        "general":    "bi-pencil-fill",
    }
    return icons.get(note_type, "bi-pencil-fill")
