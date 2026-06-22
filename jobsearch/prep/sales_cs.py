"""Sales, Customer Success & Account Management interview prep — for sales,
account-executive, customer-success, and sales-engineering resumes (the
``sales`` discipline). Distilled from Salesforce, HubSpot (SPIN, BANT),
MEDDICC.com / Force Management, Gong, and Gainsight.
"""

TRACK_SALES = {
    "slug": "sales-cs",
    "title": "Sales, CS & Account Management",
    "description": (
        "The interview that includes a live role-play. Master discovery and "
        "SPIN, objection handling, the qualification frameworks (BANT, "
        "MEDDIC/MEDDPICC), and the metrics (quota, NRR) that define sales and "
        "customer-success roles."
    ),
    "disciplines": ["sales"],
    "modules": [
        {
            "slug": "sales-roleplay",
            "title": "The Role-Play, Discovery & SPIN",
            "summary": "'Sell me this pen', discovery before pitching, and the SPIN questioning model.",
            "source_refs": "Salesforce; HubSpot (SPIN); Gong",
            "est_minutes": 25,
            "lessons": [
                {
                    "slug": "roleplay-discovery",
                    "title": "The role-play & discovery",
                    "source_refs": "Salesforce; Gong",
                    "body_md": (
                        "The **live role-play** is the differentiator: *\"sell me this pen,\"* a mock "
                        "discovery call, or a mock demo. Interviewers grade *how you react*: weak candidates "
                        "feature-dump; strong ones **ask questions first**, pitch to the surfaced need, and "
                        "**close on a clear next step**.\n\n"
                        "**Discovery** diagnoses pain before pitching. Gong's call research found top reps "
                        "ask ~11–14 questions, talk ~46% / listen ~54%, and favor open-ended questions. The "
                        "behaviors interviewers look for: discovery before pitching, problem-framing over "
                        "feature-dumping, active listening and adaptability, qualification questions, and a "
                        "clear ask for the next step."
                    ),
                    "key_takeaways": [
                        "In a role-play, ask questions before you pitch — never feature-dump.",
                        "Listen more than you talk; favor open-ended discovery questions.",
                        "Always close on a concrete next step.",
                    ],
                },
                {
                    "slug": "spin",
                    "title": "SPIN selling",
                    "source_refs": "Rackham, SPIN Selling; HubSpot",
                    "body_md": (
                        "**SPIN** (Neil Rackham) structures discovery so the buyer talks themselves into "
                        "the value:\n\n"
                        "- **S — Situation:** understand their current state.\n"
                        "- **P — Problem:** surface the pain.\n"
                        "- **I — Implication:** amplify the *cost* of that pain.\n"
                        "- **N — Need-payoff:** let the buyer state the value of solving it.\n\n"
                        "The core idea: in complex sales, ask questions until the buyer discovers the "
                        "*magnitude* of their own problem — far more persuasive than your pitching at them."
                    ),
                    "key_takeaways": [
                        "SPIN: Situation → Problem → Implication → Need-payoff.",
                        "Use Implication questions to amplify the cost of the status quo.",
                        "Let the buyer articulate the value (Need-payoff) rather than asserting it.",
                    ],
                },
            ],
        },
        {
            "slug": "sales-qualify-metrics",
            "title": "Objections, Qualification & Metrics",
            "summary": "Objection-handling frameworks, BANT/MEDDPICC qualification, and the metrics for sales vs CS.",
            "source_refs": "MEDDICC.com; HubSpot (BANT); Gainsight",
            "est_minutes": 25,
            "lessons": [
                {
                    "slug": "objections-qualification",
                    "title": "Objection handling & qualification frameworks",
                    "source_refs": "MEDDICC.com; HubSpot",
                    "body_md": (
                        "**Objections:** roughly two-thirds aren't really about price. Frameworks: **LAER** "
                        "(Listen → Acknowledge → Explore → Respond — the *Explore* step makes it strongest "
                        "for consultative B2B), **LAARC**, and beginner-friendly **Feel-Felt-Found**. For an "
                        "incumbent competitor, don't trash them — acknowledge, then differentiate on the "
                        "buyer's specific pain.\n\n"
                        "**Qualification frameworks:**\n"
                        "- **BANT** — Budget, Authority, Need, Timeline (the IBM classic).\n"
                        "- **MEDDIC → MEDDICC → MEDDPICC** (enterprise gold standard): **M**etrics, "
                        "**E**conomic buyer, **D**ecision criteria, **D**ecision process, [**P**aper "
                        "process], **I**dentify pain, **C**hampion, [**C**ompetition].\n"
                        "- **CHAMP** leads with Challenges; the **Challenger Sale** is Teach–Tailor–Take "
                        "Control."
                    ),
                    "key_takeaways": [
                        "Handle objections with LAER — the Explore step uncovers the real concern.",
                        "BANT for quick qualification; MEDDPICC for enterprise deals.",
                        "Against an incumbent, differentiate on the buyer's pain — don't bash competitors.",
                    ],
                },
                {
                    "slug": "sales-cs-metrics",
                    "title": "Metrics: sales vs customer success",
                    "source_refs": "Gainsight (NRR, QBR)",
                    "body_md": (
                        "**Sales metrics:** quota attainment (% of quota), ACV/ARR (ARR = MRR × 12), "
                        "pipeline coverage (~3–4×), win rate, sales-cycle length, and CAC.\n\n"
                        "**Customer Success / Account Management** shifts from *winning* to *keeping & "
                        "growing*: **GRR** (gross retention, excludes expansion, ≤ 100%) and **NRR/NDR** "
                        "(net retention; > 100% means existing customers grow net of churn = expansion − "
                        "contraction − churn), plus health scores, time-to-value, and NPS. The rhythm is "
                        "onboarding → adoption → **QBRs** (~60–90 days before renewal, to prove ROI and "
                        "surface expansion) → renewal → expansion.\n\n"
                        "*Scenario:* \"a key account is at risk of churn\" → diagnose via health data → find "
                        "the root cause → engage the champion/economic buyer → build a recovery plan → "
                        "quantify ROI."
                    ),
                    "key_takeaways": [
                        "Sales: quota attainment, ARR, ~3-4x pipeline coverage, win rate.",
                        "CS: NRR > 100% is the headline metric; GRR excludes expansion.",
                        "For an at-risk account: diagnose with health data, engage the champion, prove ROI.",
                    ],
                },
            ],
        },
    ],
}
