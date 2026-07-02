"""Case Interviews — for management consulting, strategy, operations, and
analytical/policy roles.

Content distilled from Cosentino, *Case in Point*; Victor Cheng (caseinterview.com,
MECE); IGotAnOffer's case framework guides; and Management Consulted's coverage of
the McKinsey Personal Experience Interview. Recommended for consulting, operations,
supply-chain, and public-policy resumes (the ``consulting`` / ``operations``
disciplines).
"""

TRACK_CASE = {
    "slug": "case-interview",
    "title": "Case Interviews",
    "description": (
        "The defining interview for consulting and many strategy/operations "
        "roles: structure an ambiguous business problem, build a MECE issue "
        "tree, do the case math, and deliver an answer-first recommendation. "
        "Covers the classic frameworks, market sizing, and worked cases."
    ),
    "disciplines": ["consulting", "operations"],
    "modules": [
        {
            "slug": "case-format",
            "title": "Format, Structure & MECE",
            "summary": (
                "Interviewer-led vs candidate-led cases, the 4-step structure, "
                "the Pyramid Principle for answer-first communication, and MECE."
            ),
            "source_refs": "Case in Point; Victor Cheng; CaseCoach",
            "est_minutes": 30,
            "lessons": [
                {
                    "slug": "case-format-structure",
                    "title": "Two formats and the 4-step structure",
                    "source_refs": "CaseCoach; Management Consulted (PEI)",
                    "body_md": (
                        "Two formats exist. **Interviewer-led** (McKinsey style): the interviewer "
                        "drives a scripted sequence — structure → an exhibit/math → a brainstorm → a "
                        "recommendation — for a uniform read across candidates. **Candidate-led** "
                        "(classic BCG/Bain): *you* drive end to end, deciding what data to request and "
                        "which hypotheses to test. In practice the style often depends on the individual "
                        "interviewer.\n\n"
                        "A 30–40 minute case runs in **four steps**:\n\n"
                        "1. **Clarify the objective** — restate the problem and confirm the success metric.\n"
                        "2. **Structure** — lay out a custom, MECE issue tree and explain your branches.\n"
                        "3. **Analyze** — work branch by branch; request data; do the math; test a hypothesis.\n"
                        "4. **Synthesize & recommend** — answer-first.\n\n"
                        "Most loops also include a **fit** portion. McKinsey's is the formal **Personal "
                        "Experience Interview (PEI)** — ~15–20 minutes deep on a *single* story (now "
                        "probing Leadership, Connection, Drive, and Growth). Prepare that with the "
                        "Behavioral track."
                    ),
                    "key_takeaways": [
                        "Know whether the firm is interviewer-led (McKinsey) or candidate-led (BCG/Bain).",
                        "Every case: clarify → structure → analyze → recommend.",
                        "Consulting loops pair the case with a fit/PEI interview — prep both.",
                    ],
                },
                {
                    "slug": "mece-pyramid",
                    "title": "MECE and the Pyramid Principle",
                    "source_refs": "Victor Cheng (MECE); Minto",
                    "body_md": (
                        "**MECE = Mutually Exclusive, Collectively Exhaustive** (Barbara Minto, McKinsey). "
                        "*Mutually exclusive* = no overlap; *collectively exhaustive* = nothing missing.\n\n"
                        "- **MECE:** age bands 0–17, 18–34, 35–54, 55+ — no overlap, everyone fits.\n"
                        "- **Not MECE:** *\"students, employees, retirees, people over 60\"* — overlap (a "
                        "65-year-old retiree is also over 60) and gaps (an unemployed 40-year-old fits "
                        "nowhere).\n\n"
                        "Communicate **top-down** using Minto's **Pyramid Principle**: lead with the "
                        "recommendation, then 3–4 grouped supporting reasons, then the evidence. A clean "
                        "closing template:\n\n"
                        "> *Recap the question → state the recommendation → give 3 reasons → name the risks "
                        "and next steps.*\n\n"
                        "Answer-first communication is itself scored — interviewers want the bottom line "
                        "before the build-up, the way you'd brief a busy executive."
                    ),
                    "key_takeaways": [
                        "Make every breakdown MECE: no overlaps, no gaps.",
                        "Lead with the answer, then 3-4 grouped reasons (Pyramid Principle).",
                        "Close with recommendation → reasons → risks → next steps.",
                    ],
                },
            ],
        },
        {
            "slug": "case-frameworks",
            "title": "Frameworks & Case Math",
            "summary": (
                "Profitability, market entry, M&A, and pricing as building "
                "blocks (not scripts), plus the mental-math toolkit and "
                "break-even."
            ),
            "source_refs": "Case in Point; IGotAnOffer",
            "est_minutes": 35,
            "lessons": [
                {
                    "slug": "classic-frameworks",
                    "title": "The classic frameworks (use as building blocks)",
                    "source_refs": "IGotAnOffer; Case in Point",
                    "body_md": (
                        "Don't recite a memorized framework — interviewers spot it instantly. Use the "
                        "classics as **building blocks** for a custom, MECE tree tailored to the prompt:\n\n"
                        "- **Profitability:** Profit = Revenue − Cost. Decompose Revenue = Price × Volume "
                        "(segment by line/geo/customer) and Cost = Fixed + Variable. Isolate the side at "
                        "fault, then drill.\n"
                        "- **Market entry:** market attractiveness (size/growth/margins) → competition → "
                        "company capabilities → financials/feasibility → entry mode (build/buy/partner, "
                        "timing).\n"
                        "- **M&A / acquisition:** target standalone value → synergies (revenue + cost) → "
                        "strategic fit/diligence risk → deal math (premium + integration cost ÷ annual net "
                        "synergies = payback).\n"
                        "- **Pricing (triangulate three lenses):** cost-based (the *floor*), competitor-based "
                        "(the *range*), value-based / willingness-to-pay (the *ceiling*).\n\n"
                        "The skill being tested is building a *bespoke* structure, prioritizing the branch "
                        "that matters, and adapting as data arrives."
                    ),
                    "key_takeaways": [
                        "Profit = Revenue (Price × Volume) − Cost (Fixed + Variable).",
                        "Tailor a custom MECE tree; never recite a canned framework.",
                        "Price between the cost floor and the value-based ceiling.",
                    ],
                },
                {
                    "slug": "case-math",
                    "title": "Case math & break-even",
                    "source_refs": "Case in Point; Victor Cheng",
                    "body_md": (
                        "Case math is mental math under observation. Narrate as you go.\n\n"
                        "- **Big numbers:** strip zeros, track magnitude with labels (k/m/b), reattach.\n"
                        "- **Percentages:** anchor on 10% and 1%, then combine (35% = 3×10% + 5%).\n"
                        "- **Fractions → %:** 1/2 = 50, 1/3 ≈ 33, 1/4 = 25, 1/8 = 12.5.\n"
                        "- **Growth / doubling:** Rule of 72 (12% → ~6 years to double).\n"
                        "- **Break-even volume = Fixed Cost ÷ (Price − Variable Cost)** — the denominator is "
                        "the unit contribution margin.\n\n"
                        "Round aggressively, **state the business implication** of each number before moving "
                        "on, and sanity-check the magnitude. Accuracy matters, but interviewers care most "
                        "that your math is *structured* and that you connect it back to the recommendation."
                    ),
                    "key_takeaways": [
                        "Strip zeros, anchor percentages on 10% and 1%, narrate aloud.",
                        "Break-even = Fixed Cost ÷ unit contribution margin.",
                        "Always translate a number into a 'so what' for the business.",
                    ],
                },
            ],
        },
        {
            "slug": "case-worked",
            "title": "Worked Cases & Evaluation",
            "summary": (
                "Market sizing end-to-end, example prompts across case types, "
                "and the dimensions firms actually score."
            ),
            "source_refs": "Case in Point; IGotAnOffer",
            "est_minutes": 30,
            "lessons": [
                {
                    "slug": "market-sizing",
                    "title": "Market sizing, worked end-to-end",
                    "source_refs": "Case in Point",
                    "body_md": (
                        "Build a **structured equation** (top-down or bottom-up), then sanity-check.\n\n"
                        "**Prompt:** *\"How many gas stations are in the US?\"*\n\n"
                        "1. Population ≈ 330M → drivers ≈ 230M.\n"
                        "2. Fill-ups per driver ≈ 50/year → total ≈ 11.5B fill-ups/year.\n"
                        "3. A station services ≈ 100,000 fill-ups/year.\n"
                        "4. Stations ≈ 11.5B ÷ 100,000 ≈ **115,000**.\n"
                        "5. *Sanity check:* the real figure is ~115k–150k — in range.\n\n"
                        "Show the equation first, state your assumptions out loud, round hard, and end with "
                        "the implication. (Benchmark numbers from prep books are *reasonable estimates*, not "
                        "official statistics — what's graded is the structure and the sanity check, not "
                        "hitting an exact figure.)"
                    ),
                    "key_takeaways": [
                        "Lay out the estimation equation before computing.",
                        "State assumptions aloud and sanity-check the magnitude at the end.",
                        "Graders reward structure over a precise number.",
                    ],
                },
                {
                    "slug": "example-cases",
                    "title": "Example prompts & how firms score you",
                    "source_refs": "IGotAnOffer; CaseCoach",
                    "body_md": (
                        "**Example prompts** (map each to a building-block structure):\n\n"
                        "- *Profitability:* \"A regional airline's profits fell 20%. Why, and what should "
                        "they do?\" → isolate revenue vs cost; drill by route/segment (price vs volume).\n"
                        "- *Market entry:* \"A US streaming company is weighing entry into India.\" → "
                        "attractiveness → competition → capabilities → break-even → entry mode.\n"
                        "- *Pricing:* \"A pharma firm is launching a novel drug — what price?\" → cost floor → "
                        "competitor range → value-based ceiling (outcomes, payer willingness to pay).\n"
                        "- *M&A:* \"Buy a smaller rival for $600M?\" → rationale → standalone value → "
                        "synergies → payback = (premium + integration) ÷ net synergies → risks.\n\n"
                        "**Scoring dimensions** (typically 1–4): **structure** (custom, MECE, prioritized), "
                        "**quantitative/analytical**, **business judgment** (often the differentiator), "
                        "**communication** (top-down synthesis), **creativity**, and **poise/coachability** "
                        "(taking a hint and adjusting). Firms want a solid baseline everywhere plus a "
                        "**\"spike\"** — McKinsey weights executive presence, BCG intellect/creativity, Bain "
                        "collaboration and fit."
                    ),
                    "key_takeaways": [
                        "Recognize the case type, then build a tailored structure for it.",
                        "Business judgment and clear synthesis are the usual differentiators.",
                        "Taking a hint well (coachability) is scored — adjust gracefully.",
                    ],
                },
            ],
        },
    ],
}
