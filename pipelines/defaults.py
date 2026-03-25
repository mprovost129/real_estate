"""
Default pipeline stages created for every new Organization.
Each entry: (name, order, probability, color, expected_days, is_won, is_lost)
"""

DEFAULT_PIPELINES = {
    "lead": {
        "name": "Lead Pipeline",
        "description": "Track leads from first contact to qualification.",
        "stages": [
            ("New Lead",          1,  5,  "#94a3b8", 1,    False, False),
            ("Attempted Contact", 2,  10, "#f59e0b", 3,    False, False),
            ("Contacted",         3,  20, "#3b82f6", 5,    False, False),
            ("Conversation",      4,  35, "#8b5cf6", 7,    False, False),
            ("Qualified",         5,  60, "#10b981", 14,   False, False),
            ("Appointment Set",   6,  75, "#06b6d4", 7,    False, False),
            ("Appointment Held",  7,  85, "#22c55e", None, False, False),
            ("Nurture",           8,  15, "#a78bfa", None, False, False),
            ("Won",               9,  100,"#16a34a", None, True,  False),
            ("Lost",              10, 0,  "#ef4444", None, False, True),
        ],
    },
    "buyer": {
        "name": "Buyer Pipeline",
        "description": "Guide buyers from consultation to closing.",
        "stages": [
            ("Consultation Scheduled", 1,  10, "#94a3b8", 7,    False, False),
            ("Consultation Completed", 2,  25, "#3b82f6", 7,    False, False),
            ("Lender Connected",       3,  35, "#f59e0b", 14,   False, False),
            ("Pre-Approved",           4,  50, "#8b5cf6", 30,   False, False),
            ("Search Active",          5,  60, "#06b6d4", 60,   False, False),
            ("Touring Homes",          6,  70, "#10b981", 30,   False, False),
            ("Offer Submitted",        7,  80, "#a78bfa", 7,    False, False),
            ("Under Contract",         8,  90, "#22c55e", 30,   False, False),
            ("Clear to Close",         9,  97, "#16a34a", 7,    False, False),
            ("Closed",                 10, 100,"#15803d", None, True,  False),
            ("Lost",                   11, 0,  "#ef4444", None, False, True),
        ],
    },
    "seller": {
        "name": "Seller Pipeline",
        "description": "Move sellers from inquiry to a closed listing.",
        "stages": [
            ("Lead Received",         1,  10, "#94a3b8", 3,    False, False),
            ("Consultation Scheduled",2,  20, "#3b82f6", 7,    False, False),
            ("Consultation Completed",3,  35, "#f59e0b", 7,    False, False),
            ("CMA Prepared",          4,  45, "#8b5cf6", 5,    False, False),
            ("Agreement Sent",        5,  55, "#06b6d4", 3,    False, False),
            ("Listing Signed",        6,  70, "#10b981", 7,    False, False),
            ("Pre-List Prep",         7,  75, "#a78bfa", 14,   False, False),
            ("Active on Market",      8,  80, "#22c55e", 30,   False, False),
            ("Under Contract",        9,  90, "#16a34a", 30,   False, False),
            ("Closed",                10, 100,"#15803d", None, True,  False),
            ("Lost",                  11, 0,  "#ef4444", None, False, True),
        ],
    },
    "recruiting": {
        "name": "Recruiting Pipeline",
        "description": "Track agent candidates from identification to onboarding.",
        "stages": [
            ("Identified",       1,  5,  "#94a3b8", 7,    False, False),
            ("Initial Outreach", 2,  15, "#f59e0b", 7,    False, False),
            ("Conversation",     3,  30, "#3b82f6", 14,   False, False),
            ("Interview",        4,  50, "#8b5cf6", 14,   False, False),
            ("Follow-Up",        5,  65, "#06b6d4", 7,    False, False),
            ("Offer Extended",   6,  80, "#10b981", 7,    False, False),
            ("Onboarded",        7,  100,"#15803d", None, True,  False),
            ("Lost",             8,  0,  "#ef4444", None, False, True),
        ],
    },
}


def create_default_pipelines(organization):
    """Create all default pipelines and stages for a new organization."""
    from .models import Pipeline, PipelineStage

    for pipeline_type, config in DEFAULT_PIPELINES.items():
        pipeline, _ = Pipeline.objects.get_or_create(
            organization=organization,
            pipeline_type=pipeline_type,
            defaults={
                "name": config["name"],
                "description": config["description"],
                "is_default": True,
            },
        )
        for (name, order, prob, color, exp_days, is_won, is_lost) in config["stages"]:
            PipelineStage.objects.get_or_create(
                pipeline=pipeline,
                name=name,
                defaults={
                    "order": order,
                    "probability": prob,
                    "color": color,
                    "expected_days": exp_days,
                    "is_won": is_won,
                    "is_lost": is_lost,
                },
            )
