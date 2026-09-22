STATUS_ACTIVE = "active"
STATUS_WON = "won"
STATUS_LOST = "lost"
STATUS_ON_HOLD = "on_hold"

# Recruiters shown in the "Recruiter View" tab. Order = display order of sub-tabs.
# Each value is a list of substrings (case-insensitive) matched against the
# Manatal user's full name returned by /users/. Multiple substrings allow
# fallback on typos / abbreviated forms. The first column is the display label
# (nickname) — it can be anything.
RECRUITERS: list[tuple[str, list[str]]] = [
    ("Alan",    ["alan lloyd bautista", "alan lloyd", "bautista"]),
    ("Louie",   ["john louie del rosario", "del rosario", "del rosaio", "john louie"]),
    ("Iyah",    ["betinna marissa silverio", "marissa silverio", "silverio"]),
    ("Ellie",   ["ellie dane lasquite", "ellie dane", "lasquite"]),
    ("Joberth", ["joberth odog", "joberth", "odog"]),
    ("Mark",    ["mark andrew lamsen", "mark andrew", "lamsen"]),
    ("Khamz",   ["jhan khamyle martin", "jhan khamyle", "khamyle"]),
]

# Manual recruiter assignment by Manatal job hash. Use this when Manatal's
# owner field is wrong/missing for a role you want pinned to a recruiter.
# Key = hash, Value = recruiter display label (must match a label in RECRUITERS).
RECRUITER_OVERRIDES: dict[str, str] = {
    "X9Y67YXY": "Iyah",  # ORGANIKA - Customer Experience Assistant (real Manatal hash, HC=2, opened 2026-04-17)
    "63VX8VVR": "Iyah",  # ORGANIKA - Customer Experience Assistant (alt hash per user; no-op if not in Manatal)
    "934V7334": "Iyah",  # ZEPP - Technical Support (Ramp, opened 2026-04-30, still open)
}

STATUS_LABELS = {
    STATUS_ACTIVE: "Open",
    STATUS_WON: "Closed Won",
    STATUS_LOST: "Closed Lost",
    STATUS_ON_HOLD: "Paused / On-Hold",
}

AGING_BUCKETS = [
    ("Fresh", 0, 14),
    ("Normal", 15, 30),
    ("Aging", 31, 45),
    ("Critical", 46, 10_000),
]

AGING_COLORS = {
    "Fresh": "#22c55e",
    "Normal": "#3b82f6",
    "Aging": "#f59e0b",
    "Critical": "#ef4444",
}

ORGANIC_VALUES = {"RAMP", "BACKFILL"}

FILL_RATE_TARGET = 0.70

# Months whose payload is locked — loaded from snapshots/ instead of recomputed.
# Format: "YYYY-MM"
LOCKED_MONTHS: set[str] = {"2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"}

# Manatal job hashes to exclude from the dashboard entirely.
# Used for duplicate/test/garbage records the user doesn't want counted anywhere.
# Roles currently in the "For Job Offer" pipeline stage, scoped by month.
# Map: hash -> {"month": "YYYY-MM", "hc": int}
# Only counts in the specified month's For Job Offer KPI.
IN_OFFER_HASHES: dict[str, dict] = {
    "Y63RR7Y5": {"month": "2026-04", "hc": 1},  # LEATHWAITE - Data Analyst (April For Job Offer)
    # 63VX8VVR (ORGANIKA - Customer Experience Asst) — moved to Ongoing Contract per user
    # Y63W7Y95 (Industrial Device Investments - Exec Asst) — candidate moved to
    # Accepted Contract in Manatal, so it auto-drops from For Job Offer once
    # Manatal syncs the offer_acceptance_date. Removed manual pin.
    # 7XWX5YWX (ZEPP Technical Support) removed — no candidate is in Offer Extended stage in Manatal
    # (1 candidate is at "Offer Accepted" — already accepted, not pending)
}

# Roles currently in the "Ongoing Contract" stage (post-offer, contract being
# negotiated / signed). Same shape as IN_OFFER_HASHES, scoped by month.
# Optional metadata (client, role, type) is used as a fallback when the hash
# isn't found in df (e.g. excluded via EXCLUDE_HASHES).
ONGOING_CONTRACT_HASHES: dict[str, dict] = {
    # 63VX8VVR (ORGANIKA) moved to CLOSED_WON_VIRTUAL_HASHES per user May tracker
}

# Virtual closed-won entries: roles that should be counted in Closed Won (and
# the SoM-side total) but don't have their own Manatal record. Used for splits
# like ORGANIKA Customer Experience where one Manatal record HC=N actually
# represents N positions in different states.
# Same shape as IN_OFFER_HASHES: hash -> {"month", "hc", "client", "role", "type"}
CLOSED_WON_VIRTUAL_HASHES: dict[str, dict] = {
    "63VX8VVR": {"month": "2026-05", "hc": 1, "client": "ORGANIKA", "role": "CUSTOMER EXPERIENCE ASSISTANT", "type": "Ramp"},  # ORGANIKA — 1 HC closed won (paired with X9Y67YXY active slot)
}

# (client_name UPPER, position_name UPPER) tuples to suppress from AUTO-DETECTED
# matches in the "Job Offer" pipeline stage. Manual IN_OFFER_HASHES entries are
# NOT filtered — they are intentional and authoritative.
EXCLUDE_IN_OFFER: set[tuple[str, str]] = {
    ("CREATIVE DENTAL PARTNERS", "DENTAL BILLING AND INSURANCE VERIFICATION SPECIALIST"),
    ("LEATHWAITE", "DATA ANALYST"),
    ("FLUENT TECHNOLOGY", "FINANCE LEAD"),
}

# (client_substring_UPPER, position_substring_UPPER, kind) tuples to suppress
# from the "All Open Roles — Aging Detail" view (and the corresponding bucket
# counts / per-type averages). Substring + case-insensitive match on the first
# two fields. `kind` must be exactly "New Logo", "Ramp", "Backfill", or None
# (None matches any kind). Use when a role is closed-won but Manatal hasn't
# propagated the offer_acceptance_date yet, or when the hash is uncertain.
EXCLUDE_FROM_AGING: set[tuple[str, str, str | None]] = {
    ("IR CHIROPRACTIC", "BUSINESS DEVELOPMENT REPRESENTATIVE", "New Logo"),
    ("C3 INGENUITY", "AI AUTOMATION ENGINEER", "New Logo"),
    ("INDUSTRIAL DEVICE INVESTMENTS", "EXECUTIVE ASSISTANT", "New Logo"),
    ("MIRION", "SENIOR CUSTOMER SERVICE", "Backfill"),
    ("ZEPP", "TECHNICAL SUPPORT", "Backfill"),
    ("ZEPP", "TECHNICAL SUPPORT", "Ramp"),                    # ZEPP Ramp also closed-won per May tracker
    ("AVARI EVENTS", "GRAPHIC DESIGNER", None),               # Closed Won May 5/29 — avoid Open double-count
    ("BLUE FEATHER DESIGNS", "DESIGN SUPPORT", None),         # Closed Won May 5/30 — avoid Open double-count
}

EXCLUDE_HASHES: set[str] = {
    "W3637VW9",  # LMTD - Animator / Motion Designer
    "Y633V9V5",  # LMTD - Senior Graphic Designer
    "X9665W7R",  # LMTD - Senior Video Editor
    "Y639WY69",  # YEEZY - Jr CSR duplicate (stale close_at predates open_at)
    "V6YWV63R",  # TLC Solutions - Procurement Specialist (per user, not a real April addition)
    # RY7VY56R (IR Chiropractic - Virtual Assistant/BDR) — per user, IS in April SOM (carry-over). Removed from exclude.
    "Y6R5X345",  # OPTIMA Energy - Fullstack Software Developer (per user, not a real April addition)
    "W354V6Y6",  # OPTIMA Energy - Fullstack Software Developer (per user, duplicate of 5WR9XYX3)
    "7XW7XVW3",  # PERCEPTICS - Marketing Coordinator (per user, duplicate of 63VX6W75)
    "63VX8VVR",  # ORGANIKA - Customer Experience Assistant (Manatal duplicate; tracked separately via IN_OFFER_HASHES for May)
    "V6Y9X78R",  # ORGANIKA - Customer Experience Assistant (Manatal duplicate of X9Y67YXY)
}

# Manual status overrides keyed by Manatal job `hash` code.
# These override whatever status the Manatal API returns.
STATUS_OVERRIDES: dict[str, str] = {
    # Closed Lost / Cancelled
    "63378XVR": STATUS_LOST,     # Thatcher Technology Group - Senior Software Developer
    "V6637XV6": STATUS_LOST,     # P&D Painting CT Inc. - Digital Marketing Specialist
    "5WWY74Y5": STATUS_LOST,     # P&D Painting CT Inc. - Sales Representative
    "8XX3R893": STATUS_LOST,     # P&D Painting CT Inc. - Estimator
    # Paused / On Hold
    "3WW6Y4Y8": STATUS_ON_HOLD,  # TLC Solutions - Client Care Coordinator
    "Y665Y78V": STATUS_ON_HOLD,  # Soleire - Part-Time AutoCAD Operator
    "8XX6V4RR": STATUS_ON_HOLD,  # Fiscus Billing Inc. - Medical Billing Data Entry Specialist
    "X99VYVRY": STATUS_ON_HOLD,  # WEBARC - Sales Development Representative (IT)
    "W33R5V59": STATUS_ON_HOLD,  # WEBARC - Senior Sales Development Representative (IT)
    "6337YY35": STATUS_ON_HOLD,  # Save On Branson - Part-time Data Specialist
    "W36639R9": STATUS_ON_HOLD,  # Defined Marketing - WordPress Developer
    # Paused (April 2026) — per user
    "W35934X6": STATUS_ON_HOLD,  # TLC Solutions - Procurement Specialist
    "63VX6W75": STATUS_ON_HOLD,  # PERCEPTICS - Marketing Coordinator
    "L3V9WYXW": STATUS_ON_HOLD,  # ZEPP - Technical Support (legacy record, paused April 2026)
    # 5WR9XYX3 (OPTIMA) and X96484VR (EARLY PR) now tagged on_hold in Manatal — no override needed
    # Force-active (not paused) — Manatal flagged on_hold but per user these
    # should NOT count as paused for any month.
    "W3637VW9": STATUS_ACTIVE,   # LMTD - Animator / Motion Designer
    "Y633V9V5": STATUS_ACTIVE,   # LMTD - Senior Graphic Designer
    "X9665W7R": STATUS_ACTIVE,   # LMTD - Senior Video Editor
    "Y639WY69": STATUS_ACTIVE,   # YEEZY - Junior CSR (duplicate record, close_at predates open_at)
    "X9Y67YXY": STATUS_ACTIVE,   # ORGANIKA Customer Experience Asst — 1 HC active (other slot is virtual closed-won via 63VX8VVR)
    # V6Y434W8 (DR. YELTON) — per user, paused but counts in SoM; uses SOM_OPEN_THROUGH_OVERRIDES instead of status override
    "V6YXVRY8": STATUS_WON,      # YEEZY Jr CSR — offer accepted in May, not yet started (force out of Open)
    "934V7334": STATUS_WON,      # ZEPP Technical Support (Ramp) — offer accepted in May, not yet started (force out of Open)
    # Force-won — per user, these are in Closed Won (offer accepted) and should
    # NOT appear in the Aging detail / Open KPI / Business view.
    "8XX44893": STATUS_WON,      # IR Chiropractic - Virtual Assistant / BDR
    "8X3W7763": STATUS_WON,      # C3 Ingenuity - AI Automation Engineer
    # Y63W7Y95 (Industrial Device Exec Asst) — moved to For Job Offer per user; status reverts to Manatal's value
    "7XWX5YWX": STATUS_WON,      # ZEPP - Technical Support (the closed-won record of the two)
    "8X79XV9R": STATUS_WON,      # MIRION - Senior CSR
}

# Manual event-date overrides keyed by Manatal job `hash`.
# Used to set the effective pause/lost date when Manatal's close_at is missing
# or wrong. The format is ISO date "YYYY-MM-DD".
# This overrides the close_at column in the dataframe.
# Manual role-type overrides keyed by Manatal job `hash`.
# Values: "New Logo", "Ramp", or "Backfill".
# Overrides the default "first job per org -> New Logo" derivation.
TYPE_OVERRIDES: dict[str, str] = {
    # Closed Lost (Feb 2026)
    "63378XVR": "Ramp",       # Thatcher Tech Group - Senior Software Developer
    "V6637XV6": "New Logo",   # P&D Painting CT - Digital Marketing Specialist
    "5WWY74Y5": "New Logo",   # P&D Painting CT - Sales Representative
    "8XX3R893": "New Logo",   # P&D Painting CT - Estimator
    # Paused (Feb 2026)
    "3WW6Y4Y8": "Ramp",       # TLC Solutions - Client Care Coordinator
    "Y665Y78V": "New Logo",   # Soleire - Part-Time AutoCAD Operator
    "8XX6V4RR": "Ramp",       # Fiscus Billing - Medical Billing Data Entry (Organic per user)
    "X99VYVRY": "New Logo",   # WEBARC - SDR (IT)
    "W33R5V59": "New Logo",   # WEBARC - Senior SDR (IT)
    "6337YY35": "Backfill",   # Save On Branson - Part-Time Data Specialist
    "W36639R9": "New Logo",   # Defined Marketing - WordPress Developer
    # Closed Won (Feb 2026) — YEEZY all classified as New Logo per user
    "7XXR83VX": "New Logo",   # YEEZY - QA/Trainer
    "W337RV49": "New Logo",   # YEEZY - Fraud Specialist
    "4RR39W65": "New Logo",   # YEEZY - Senior CSR
    "Y66W9X7V": "New Logo",   # YEEZY - Junior CSR
    "W359XYXW": "Backfill",   # YEEZY - Fraud Specialist (March Additional, per user)
    # Per user: these are Organic / Backfill
    "5WR9XYX3": "Backfill",   # OPTIMA Energy - Fullstack Software Developer
    "W35YWV39": "Backfill",   # IR Chiropractic - Business Development Representative (5/20 record)
    "3W6V7R6V": "Backfill",   # WHALE SWIM - Part-Time CSR & HR Admin Support
    "V6YR34W6": "Backfill",   # ORGANIKA - Sales Admin Assistant
    # July tagging per user
    "W3484Y36": "New Logo",   # AUTO ACTION - Content Writer & Digital Producer
    "X948RYXR": "Backfill",   # ADAUGEO - Azure Cloud Engineer
    "Y658W869": "Backfill",   # BLUE FEATHER DESIGN - Design Support Specialist (CAD)
    "8X9R764R": "Ramp",       # CREATIVE DENTAL PARTNER - Dental Account Receivable
}

# Name-based type overrides for when the hash isn't known.
# Key: (client_substring UPPER, position_substring UPPER). Value: "New Logo", "Ramp", or "Backfill".
# Applied AFTER hash-based TYPE_OVERRIDES, so a hash entry wins if both match.
NAME_BASED_TYPE_OVERRIDES: dict[tuple[str, str], str] = {
    ("DR. YELTON", "PART-TIME SEO MARKETING SPECIALIST"): "Ramp",
    ("AUDITDATA", "TECH LEAD"): "New Logo",
    ("AUDIT DATA", "TECH LEAD"): "New Logo",
    ("AUDITDATA", "SENIOR FULL STACK"): "New Logo",
    ("AUDIT DATA", "SENIOR FULL STACK"): "New Logo",
    ("AUDITDATA", "GENERAL QA ENGINEER"): "New Logo",
    ("AUDIT DATA", "GENERAL QA ENGINEER"): "New Logo",
    ("AUDITDATA", "AGILE PROJECT LEAD"): "New Logo",
    ("AUDIT DATA", "AGILE PROJECT LEAD"): "New Logo",
    ("AUDITDATA", "PRODUCT OWNER"): "New Logo",
    ("AUDIT DATA", "PRODUCT OWNER"): "New Logo",
    ("AUDITDATA", "DATA ARCHITECT"): "New Logo",
    ("AUDIT DATA", "DATA ARCHITECT"): "New Logo",
}

# Manual offer-acceptance-date overrides keyed by Manatal job `hash`.
# Used to move a role to a different month's Closed Won bucket.
OFFER_ACCEPTANCE_OVERRIDES: dict[str, str | None] = {
    "X99X48Y3": "2026-01-29",  # MIRION - Collections Specialist (per user, in Jan CW)
    "4R8453Y5": None,          # TLC Solutions Specialist (HC=1) — duplicate of 8X754V7R
    "8X754V7R": None,          # TLC Solutions Specialist (HC=1) — Manatal had offer=12/29 (= open date), invalid
    "W359XYXW": "2026-03-15",  # YEEZY Fraud Specialist (HC=1) — per user, March Closed Won as Backfill
    "8X79XV9R": "2026-05-05",  # MIRION Sr CSR — per user, Offer Accepted in May
    # Y63W7Y95 (Industrial Device Exec Asst) — moved to For Job Offer (IN_OFFER_HASHES) per user
    "X9Y67YXY": None,          # ORGANIKA Customer Experience Asst — per user, still an open role (clear Manatal's offer date)
    "63VX8VVR": None,          # ORGANIKA Customer Experience Asst — per user, offer extended (not accepted); clear Manatal's offer date
}

# Headcount reduction applied ONLY to current-state metrics (Open KPI, Aging detail,
# Business view). SoM and historical metrics keep the full headcount. Use when a role
# has positions split across hashes: e.g. X9Y67YXY has HC=2 in SoM, but 1 of those
# is tracked as For Job Offer via 63VX8VVR, leaving 1 still actively being filled.
AGING_HC_REDUCTION: dict[str, int] = {
    "X9Y67YXY": 1,  # ORGANIKA Customer Experience Asst — 1 HC currently in For Job Offer (via 63VX8VVR)
}

# Manual headcount overrides keyed by Manatal job `hash`.
# Used when Manatal's headcount differs from the user's source-of-truth tracker.
HEADCOUNT_OVERRIDES: dict[str, int] = {
    "V6637XV6": 1,  # P&D Painting CT - Digital Marketing Specialist (Manatal had 2)
    "3WR87Y68": 1,  # Thatcher - Senior QA Software Engineer (per user, HC=1)
    "63VX6W75": 1,  # PERCEPTICS - Marketing Coordinator (per user, HC=1)
    "X9Y67YXY": 2,  # ORGANIKA - Customer Experience Assistant (Manatal HC=2; split via AGING_HC_REDUCTION + virtual closed won)
    # 7XWX5YWX (ZEPP) keeps HC=2; the For Job Offer KPI shows HC=1 via IN_OFFER_HASHES
}

# Manual open-date overrides keyed by Manatal job `hash`.
# Used to move a role out of one month's "Additional this month" into another.
OPEN_AT_OVERRIDES: dict[str, str] = {
    "4R8453Y5": "2026-03-01",  # TLC Solutions Specialist (HC=1) — moved to March per user
    "X965R96Y": "2026-02-01",  # BLUE SKY Surface Designer — per user, not Jan-opened
    "3W6754VV": "2026-02-28",  # YEEZY Senior CSR (HC=2) — per user, in Feb additional
    "W359XYXW": "2026-03-15",  # YEEZY Fraud Specialist (HC=1) — per user, in March additional as Backfill
    "7XWX5YWX": "2026-04-30",  # ZEPP Technical Support (HC=2) — per user, opens 4/30 (carry-over to May SOM)
    "RY7VY56R": "2026-03-15",  # IR Chiropractic - Virtual Assistant/BDR — per user, counts as April SOM (carry-over)
    # X9Y67YXY (ORGANIKA Customer Experience Asst) — Manatal already has open=2026-04-17, no override needed
}

# Manual "still open through" overrides keyed by Manatal job `hash`.
# Used ONLY for SOM/open-during filtering. Lets a paused role be classified
# in (e.g.) January's Paused list while still appearing in February SOM as
# a carry-over (because the role remains an open requirement to fill).
SOM_OPEN_THROUGH_OVERRIDES: dict[str, str] = {
    "3WW6Y4Y8": "2026-02-28",  # TLC Solutions Client Care - paused Jan, still open carry-over to Feb
    "8X39R7Y3": "2026-03-31",  # AMERICAN DATA - Clinical Support Specialist
    "934V9VY4": "2026-03-31",  # IAULA - Virtual Assistant
    "93R7XYXY": "2026-03-31",  # MOON - Digital Marketing Specialist (Part-Time)
    "Y63RR7Y5": "2026-04-30",  # LEATHWAITE - Data Analyst (April For Job Offer; NOT in May SOM)
    "L3V9WYXW": "2026-03-31",  # ZEPP legacy record — paused April only, not in April SOM
    "X96484VR": "2026-05-31",  # EARLY PR - Part-time Admin Assistant — on_hold in Manatal but per user, counts in April + May SOM
    "5WR9XYX3": "2026-05-31",  # OPTIMA Energy - Fullstack Software Developer — on_hold in Manatal but per user, counts in May SOM
    "X9Y67YXY": "2026-05-31",  # ORGANIKA Customer Experience Asst — per user, open through May
    "V6Y434W8": "2026-05-31",  # DR. YELTON Part-Time SEO Marketing Specialist — Manatal on_hold but counts in May SOM (per user)
}

EVENT_DATE_OVERRIDES: dict[str, str] = {
    # Per user: these were paused in February 2026 (Manatal close_at was null)
    "3WW6Y4Y8": "2026-02-15",  # TLC Solutions - Client Care Coordinator (paused in Feb per user)
    "Y665Y78V": "2026-02-15",  # Soleire - Part-Time AutoCAD Operator
    "8XX6V4RR": "2026-02-15",  # Fiscus Billing - Medical Billing Data Entry
    "W36639R9": "2026-02-15",  # Defined Marketing - WordPress Developer
    # Per user: these were closed lost / cancelled in February 2026
    "63378XVR": "2026-02-15",  # Thatcher Tech Group - Senior Software Developer
    "V6637XV6": "2026-02-15",  # P&D Painting CT - Digital Marketing Specialist
    "8XX3R893": "2026-02-15",  # P&D Painting CT - Estimator
    # 5WWY74Y5 (P&D Sales Rep) already has close_at = 2026-02-05; no override needed
    # TLC Solutions Specialist (HC=1, opened Dec 29) — per user, was open through January
    "8X754V7R": "2026-01-31",  # TLC Solutions - Solutions Specialist
    # MIRION Billing Analyst (HC=2) — Manatal close=2025-10-06 was BEFORE open=2025-12-11.
    # Override close to match offer_acc (2026-02-09) so it carries over Dec→Jan→Feb correctly.
    "6338RW4R": "2026-02-09",
    # IAULA Virtual Assistant — Manatal close=2026-02-17 was BEFORE open=2026-03-18.
    # Override to put pause in March (per user, Mar paused).
    "934V399Y": "2026-03-25",
    # April paused (per user)
    "W35934X6": "2026-04-15",  # TLC Solutions Procurement Specialist
    "63VX6W75": "2026-04-15",  # PERCEPTICS Marketing Coordinator
    "L3V9WYXW": "2026-04-15",  # ZEPP Technical Support (legacy record)
    # 5WR9XYX3 and X96484VR — Manatal now provides the pause date via close_at / updated_at
}
