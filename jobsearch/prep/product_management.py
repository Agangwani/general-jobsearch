"""Product Management interview prep — for PM / TPM resumes (the ``product``
discipline). Distilled from McDowell & Bavaro, *Cracking the PM Interview*;
Lewis Lin, *Decode and Conquer* (CIRCLES); Exponent; ProductPlan; and Reforge.
"""

TRACK_PM = {
    "slug": "product-management",
    "title": "Product Management Interviews",
    "description": (
        "Product sense, execution/metrics, estimation, and strategy — the PM "
        "loop. Learn the CIRCLES design framework, how to diagnose a metric "
        "drop, prioritization with RICE, and the north-star/funnel metrics."
    ),
    "disciplines": ["product"],
    "modules": [
        {
            "slug": "pm-product-sense",
            "title": "Product Sense & Design",
            "summary": "The CIRCLES framework, 'design/improve a product' questions, and what's scored.",
            "source_refs": "Cracking the PM Interview; Lewis Lin (CIRCLES)",
            "est_minutes": 30,
            "lessons": [
                {
                    "slug": "circles",
                    "title": "The CIRCLES method for product design",
                    "source_refs": "Lewis Lin, Decode and Conquer",
                    "body_md": (
                        "Almost every loop reduces to **product sense, execution, and behavioral** "
                        "(branded differently: Google \"product design,\" Meta \"product sense\"). For "
                        "*\"design a product for X\"* / *\"improve Y\"*, the standard scaffold is "
                        "**CIRCLES** (Lewis Lin):\n\n"
                        "- **C** — Comprehend the situation (clarify scope, constraints, goal).\n"
                        "- **I** — Identify the customer (pick a segment).\n"
                        "- **R** — Report the customer's needs (their jobs-to-be-done / pain points).\n"
                        "- **C** — Cut through prioritization (which needs matter most, and why).\n"
                        "- **L** — List solutions.\n"
                        "- **E** — Evaluate trade-offs.\n"
                        "- **S** — Summarize your recommendation.\n\n"
                        "The simpler mental flow underneath it: **user segments → pain points → solutions → "
                        "prioritize → success metrics.** What's scored: customer empathy, structured "
                        "thinking, justified prioritization, and creativity."
                    ),
                    "key_takeaways": [
                        "CIRCLES: Comprehend, Identify, Report needs, Cut/prioritize, List, Evaluate, Summarize.",
                        "Always anchor on a specific user segment and their jobs-to-be-done.",
                        "Prioritize explicitly and justify the trade-offs.",
                    ],
                },
                {
                    "slug": "pm-design-questions",
                    "title": "Example product-sense questions",
                    "source_refs": "Exponent",
                    "body_md": (
                        "Practice these aloud with CIRCLES:\n\n"
                        "- \"Design a product for the visually impaired.\"\n"
                        "- \"Improve Google Maps / Instagram.\"\n"
                        "- \"Design an alarm clock for the deaf.\"\n"
                        "- \"Design a fridge for the elderly.\"\n\n"
                        "Strong answers pick a segment fast, name concrete pain points, propose a few "
                        "differentiated solutions, prioritize one, and define how you'd measure success. "
                        "Avoid jumping straight to features before you've identified the user and the need."
                    ),
                    "key_takeaways": [
                        "Pick a user and a need before proposing features.",
                        "Offer a few solutions, then prioritize one with a reason.",
                        "Close every design answer with a success metric.",
                    ],
                },
            ],
        },
        {
            "slug": "pm-execution",
            "title": "Execution, Metrics & Prioritization",
            "summary": "Diagnosing a metric drop, north-star/funnel metrics, estimation, and RICE.",
            "source_refs": "Reforge; ProductPlan; Intercom",
            "est_minutes": 30,
            "lessons": [
                {
                    "slug": "metrics-diagnosis",
                    "title": "Metrics, north star & diagnosing a drop",
                    "source_refs": "Reforge; Dave McClure (AARRR)",
                    "body_md": (
                        "**Metric frameworks:** the **AARRR \"pirate\" funnel** (Acquisition, Activation, "
                        "Retention, Referral, Revenue) and the **north-star metric** — the single enduring "
                        "measure of core value (Airbnb = nights booked; Spotify = time listening), protected "
                        "by counter-metrics so it can't be gamed.\n\n"
                        "**\"Metric X dropped Y% — diagnose it\":**\n"
                        "1. **Clarify & quantify** — sudden vs gradual? how big?\n"
                        "2. **Rule out data/logging bugs** first.\n"
                        "3. **Internal vs external** — a release/bug/outage/pricing change vs a "
                        "competitor/seasonality/PR event.\n"
                        "4. **Segment** — platform, geo, cohort, new vs existing users.\n"
                        "5. **Walk the funnel** to the specific step that dropped.\n\n"
                        "Good metrics are simple, unambiguous, actionable, and hard to game."
                    ),
                    "key_takeaways": [
                        "Know AARRR and the north-star metric (with counter-metrics).",
                        "Diagnose drops: clarify → rule out data bugs → internal/external → segment → funnel.",
                        "A metric you can't tie to user value or that's easily gamed is a weak metric.",
                    ],
                },
                {
                    "slug": "rice-estimation",
                    "title": "Prioritization (RICE) & estimation",
                    "source_refs": "Intercom (RICE); Exponent",
                    "body_md": (
                        "**RICE** (created at Intercom) scores initiatives:\n\n"
                        "> **Score = (Reach × Impact × Confidence) ÷ Effort**\n\n"
                        "where Reach = # per period, Impact = 3/2/1/0.5/0.25, Confidence = 100/80/50%, "
                        "Effort = person-months. Alternatives: **Kano** (delighters vs must-haves), "
                        "**MoSCoW** (release scoping), and a simple **Value vs Effort** matrix.\n\n"
                        "**Estimation / market sizing** (\"how many pizzas are sold in the US per year?\", "
                        "\"how many queries does Google answer per second?\"): build a structured equation, "
                        "state assumptions out loud, round aggressively, and sanity-check — exactly like the "
                        "case-interview market-sizing approach."
                    ),
                    "key_takeaways": [
                        "RICE = (Reach × Impact × Confidence) ÷ Effort.",
                        "Match the prioritization tool to the question (Kano, MoSCoW, value/effort).",
                        "Estimation rewards a clear equation and stated assumptions, not a precise number.",
                    ],
                },
            ],
        },
    ],
}
