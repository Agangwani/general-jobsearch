"""Design interview prep — for product/UX designers and architecture resumes
(the ``design`` discipline). Distilled from Nielsen Norman Group (10 heuristics,
design thinking), the Interaction Design Foundation, the UK Design Council
(Double Diamond), W3C WAI (WCAG/POUR), and Exponent.
"""

TRACK_DESIGN = {
    "slug": "design",
    "title": "Design Interviews",
    "description": (
        "Portfolio review, the app/whiteboard design challenge, and design "
        "critique. Learn a whiteboard process, Nielsen's usability heuristics, "
        "accessibility (POUR), and how to present decisions — not just pixels."
    ),
    "disciplines": ["design"],
    "modules": [
        {
            "slug": "design-portfolio-challenge",
            "title": "Portfolio & the Whiteboard Challenge",
            "summary": "Telling a portfolio story and a repeatable process for the live design challenge.",
            "source_refs": "Exponent; NN/g; Design Council",
            "est_minutes": 30,
            "lessons": [
                {
                    "slug": "portfolio",
                    "title": "The portfolio review (the most important round)",
                    "source_refs": "Exponent; Greever, Articulating Design Decisions",
                    "body_md": (
                        "Walk through 1–3 case studies as a **story**: **problem/context → your role → "
                        "process (research, ideation, iterations) → key decisions & why → outcome/impact.** "
                        "Interviewers care most about your **decisions and the alternatives you explored**, "
                        "not final-UI polish.\n\n"
                        "Best practices:\n"
                        "- Show **process** (research, journey maps, sketches, test results), not just the "
                        "final screens.\n"
                        "- **Quantify impact** (conversion lift, task-time reduction, fewer support tickets).\n"
                        "- Explain trade-offs and **what you'd do differently**.\n"
                        "- **Depth over breadth** — 3–5 strong end-to-end cases beat a dozen thin ones.\n\n"
                        "(Architecture portfolios follow the same arc — concept → constraints → iterations → "
                        "built outcome — emphasizing the decisions behind the drawings.)"
                    ),
                    "key_takeaways": [
                        "Tell each case as problem → role → process → decisions → impact.",
                        "Show the process and alternatives, not just polished final screens.",
                        "Quantify outcomes and go deep on a few cases.",
                    ],
                },
                {
                    "slug": "whiteboard",
                    "title": "The whiteboard / app design challenge",
                    "source_refs": "NN/g (Design Thinking); Design Council (Double Diamond)",
                    "body_md": (
                        "For *\"design an app for X\"* / *\"redesign Y,\"* you're graded on **process and "
                        "real-time communication**, not finished fidelity. A reliable sequence:\n\n"
                        "1. **Clarify** the problem, users, platform, and success — *don't sketch yet*.\n"
                        "2. **Identify users & goals** (a persona, jobs-to-be-done).\n"
                        "3. **Map the user journey / use cases.**\n"
                        "4. **Ideate / sketch** — diverge, think aloud.\n"
                        "5. **Prioritize one primary flow** (and justify it).\n"
                        "6. **Low-fi wireframes.**\n"
                        "7. **Trade-offs & edge cases** (empty/error/loading states, accessibility).\n"
                        "8. **Success metrics.**\n\n"
                        "This maps onto **Design Thinking** (Empathize → Define → Ideate → Prototype → Test) "
                        "and the **Double Diamond** (Discover → Define → Develop → Deliver — diverge then "
                        "converge, twice)."
                    ),
                    "key_takeaways": [
                        "Clarify users, platform, and success before sketching.",
                        "Diverge then converge; prioritize one primary flow and justify it.",
                        "Always cover edge cases (empty/error/loading) and success metrics.",
                    ],
                },
            ],
        },
        {
            "slug": "design-heuristics-critique",
            "title": "Heuristics, Accessibility & Critique",
            "summary": "Nielsen's 10 heuristics, WCAG/POUR accessibility, and a structure for design critique.",
            "source_refs": "NN/g; W3C WAI",
            "est_minutes": 25,
            "lessons": [
                {
                    "slug": "heuristics-accessibility",
                    "title": "Usability heuristics & accessibility",
                    "source_refs": "NN/g (10 Heuristics); W3C WAI (WCAG)",
                    "body_md": (
                        "Reference these to justify decisions instead of taste.\n\n"
                        "**Nielsen's 10 Usability Heuristics:** (1) visibility of system status; (2) match "
                        "between system and the real world; (3) user control and freedom; (4) consistency "
                        "and standards; (5) error prevention; (6) recognition rather than recall; (7) "
                        "flexibility and efficiency of use; (8) aesthetic and minimalist design; (9) help "
                        "users recognize, diagnose, and recover from errors; (10) help and documentation.\n\n"
                        "**Accessibility — WCAG's POUR:** Perceivable, Operable, Understandable, Robust. "
                        "Practical AA basics: contrast ≥ 4.5:1 (normal text) / 3:1 (large); full keyboard "
                        "operability with a visible focus state; text alternatives for images; don't rely on "
                        "color alone; large enough touch targets."
                    ),
                    "key_takeaways": [
                        "Cite Nielsen's heuristics to ground critique in principles, not taste.",
                        "Accessibility = POUR (Perceivable, Operable, Understandable, Robust).",
                        "Know AA basics: 4.5:1 contrast, keyboard operability, don't rely on color alone.",
                    ],
                },
                {
                    "slug": "critique",
                    "title": "Design critique structure",
                    "source_refs": "NN/g",
                    "body_md": (
                        "When asked to critique a product (or a peer's work), tie every comment to a "
                        "**user/business goal or a heuristic**, never to taste:\n\n"
                        "1. State the design's **goal & user**.\n"
                        "2. What **works**, and why.\n"
                        "3. What **doesn't**, and why (link to a specific heuristic or user goal).\n"
                        "4. **Actionable** suggestions.\n\n"
                        "Critique the *design*, not the *designer*; be specific (\"low contrast / weak "
                        "hierarchy / too many steps,\" not \"it feels clunky\"); and balance positives with "
                        "negatives. Common prompts: \"critique Instagram,\" \"your favorite app and how "
                        "you'd improve it,\" \"what would you improve about our product?\""
                    ),
                    "key_takeaways": [
                        "Critique: goal/user → what works → what doesn't (cite a heuristic) → suggestions.",
                        "Critique the design, not the designer; be specific.",
                        "Tie every point to a user goal or usability principle.",
                    ],
                },
            ],
        },
    ],
}
