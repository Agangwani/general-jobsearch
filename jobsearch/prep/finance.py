"""Finance & Investment Banking interview prep — for IB, FP&A, accounting,
insurance/actuarial, and real-estate finance resumes (the ``finance`` discipline).

Distilled from Wall Street Prep, Breaking Into Wall Street / Mergers & Inquisitions,
Corporate Finance Institute, and Rosenbaum & Pearl, *Investment Banking*. The
technical answers below are the standard ones; verify exact figures against the
source books before relying on them in a live interview.
"""

TRACK_FINANCE = {
    "slug": "finance",
    "title": "Finance & Investment Banking",
    "description": (
        "Technical interview prep for banking, FP&A, accounting, and finance "
        "roles: how the three statements link, walking through a DCF, valuation "
        "methods, the enterprise-to-equity bridge, accretion/dilution, LBO "
        "basics, and the fit questions that decide superdays."
    ),
    "disciplines": ["finance"],
    "modules": [
        {
            "slug": "accounting-foundations",
            "title": "Accounting & the Three Statements",
            "summary": (
                "How the income statement, balance sheet, and cash flow "
                "statement link — the single most-tested IB concept — plus the "
                "classic 'depreciation +$10' walkthrough."
            ),
            "source_refs": "Wall Street Prep; CFI",
            "est_minutes": 30,
            "lessons": [
                {
                    "slug": "three-statements",
                    "title": "How the three statements link",
                    "source_refs": "CFI; Wall Street Prep",
                    "body_md": (
                        "The most common technical question, in every flavor:\n\n"
                        "- **Net income** flows from the bottom of the income statement to the top of the "
                        "**cash flow statement** and into **retained earnings** on the balance sheet.\n"
                        "- The cash flow statement adjusts net income for **non-cash items** (D&A) and "
                        "**changes in working capital** to arrive at the net change in cash.\n"
                        "- Ending cash lands on the **balance sheet**, which must **balance**: Assets = "
                        "Liabilities + Equity.\n\n"
                        "Master the linkage well enough to walk it both forwards and backwards, because "
                        "the follow-up is always a perturbation question (below)."
                    ),
                    "key_takeaways": [
                        "Net income → cash flow statement → retained earnings.",
                        "CFS adjusts NI for D&A and working-capital changes to get ending cash.",
                        "Ending cash hits the balance sheet, which must balance (A = L + E).",
                    ],
                },
                {
                    "slug": "depreciation-walkthrough",
                    "title": "'Depreciation goes up $10' — walk the statements",
                    "source_refs": "Wall Street Prep; BIWS",
                    "body_md": (
                        "**Q: Depreciation increases by $10. Walk through the three statements (25% tax).**\n\n"
                        "- **Income statement:** pre-tax income −$10; at 25% tax, **net income −$7.50**.\n"
                        "- **Cash flow statement:** start from NI −$7.50, **add back $10** of non-cash "
                        "depreciation → **cash +$2.50**.\n"
                        "- **Balance sheet:** cash +$2.50 and PP&E −$10 → assets −$7.50; retained earnings "
                        "−$7.50 → **it balances**.\n\n"
                        "Shortcut: the cash change equals **depreciation × tax rate** ($10 × 25% = $2.50). "
                        "At a 40% tax rate the answer is NI −$6, cash +$4. Knowing the shortcut *and* being "
                        "able to walk every line is what they're testing."
                    ),
                    "key_takeaways": [
                        "Net cash change from a non-cash expense = expense × tax rate.",
                        "Add non-cash items back on the cash flow statement.",
                        "Confirm the balance sheet still balances at the end.",
                    ],
                },
            ],
        },
        {
            "slug": "valuation",
            "title": "Valuation: DCF, Comps & the EV Bridge",
            "summary": (
                "Walk me through a DCF, the three valuation methods and their "
                "ranking, the enterprise-to-equity-value bridge, and WACC."
            ),
            "source_refs": "Wall Street Prep; Rosenbaum & Pearl",
            "est_minutes": 35,
            "lessons": [
                {
                    "slug": "dcf",
                    "title": "Walk me through a DCF",
                    "source_refs": "Wall Street Prep; CFI",
                    "body_md": (
                        "**Five steps:**\n\n"
                        "1. **Project unlevered free cash flow** = EBIT × (1 − tax) + D&A − CapEx − ΔNWC, "
                        "for 5–10 years.\n"
                        "2. **Compute WACC** = E/V·(cost of equity) + D/V·(cost of debt)·(1 − tax), with "
                        "cost of equity via CAPM = R_f + β·(equity risk premium).\n"
                        "3. **Terminal value** via Gordon growth [TV = FCF·(1+g)/(WACC − g)] or an exit "
                        "multiple.\n"
                        "4. **Discount** all FCFs and the terminal value to today at WACC.\n"
                        "5. **Sum** to enterprise value, then bridge to equity value and per-share value.\n\n"
                        "*Unlevered* means before the effect of debt/interest — that's why you discount at "
                        "WACC (the blended cost of all capital), not the cost of equity."
                    ),
                    "key_takeaways": [
                        "UFCF = EBIT×(1−tax) + D&A − CapEx − ΔNWC.",
                        "Discount at WACC; terminal value via Gordon growth or exit multiple.",
                        "Sum to enterprise value, then bridge to equity value.",
                    ],
                },
                {
                    "slug": "methods-and-bridge",
                    "title": "Valuation methods, ranking & the EV↔equity bridge",
                    "source_refs": "BIWS; Rosenbaum & Pearl",
                    "body_md": (
                        "**Three methods:** comparable companies (trading comps), precedent transactions, "
                        "and DCF. Typical ranking of the *output*: **precedent transactions ≥ DCF ≥ trading "
                        "comps**, because precedents bake in a **control premium**. It isn't ironclad — the "
                        "best answer is to *triangulate* across all three.\n\n"
                        "**The enterprise-to-equity bridge:**\n\n"
                        "> **Enterprise Value = Equity Value + Total Debt + Preferred + Minority Interest − "
                        "Cash.**\n\n"
                        "Add non-common claims; subtract cash. A common trick: *\"If a company raises debt, "
                        "what happens to EV?\"* → **nothing** — cash and debt both rise and net out. Same for "
                        "issuing equity (cash and equity value both rise).\n\n"
                        "**Accretion/dilution:** for an all-stock deal with no premium or synergies, it's "
                        "**accretive if the acquirer's P/E > the target's P/E**, dilutive if lower (it gets "
                        "more complex once you add premium, synergies, or cash)."
                    ),
                    "key_takeaways": [
                        "EV = Equity Value + Debt + Preferred + Minority Interest − Cash.",
                        "Precedents usually price highest (control premium); triangulate the three methods.",
                        "All-stock, no synergies: accretive if acquirer P/E > target P/E.",
                    ],
                },
            ],
        },
        {
            "slug": "lbo-and-fit",
            "title": "LBO Basics, FP&A & Fit",
            "summary": (
                "The LBO at a high level (IRR, MOIC, the paper LBO), the FP&A "
                "twist (budget vs forecast, variance), and the fit questions "
                "that often decide the offer."
            ),
            "source_refs": "Wall Street Prep; CFI",
            "est_minutes": 30,
            "lessons": [
                {
                    "slug": "lbo",
                    "title": "LBO basics & the paper LBO",
                    "source_refs": "Wall Street Prep (paper LBO)",
                    "body_md": (
                        "A **leveraged buyout**: a PE firm buys a company mostly with **debt** plus some "
                        "equity. Leverage amplifies equity returns, and paying down debt over the hold "
                        "shifts value to equity. Returns are measured by **IRR** and **MOIC** (Multiple on "
                        "Invested Capital = exit equity ÷ entry equity). A typical target is ~20–25% IRR / "
                        "~2.5–3.0× over five years.\n\n"
                        "**Paper LBO (do it in your head):**\n"
                        "1. Entry enterprise value = entry multiple × EBITDA; split into debt and equity "
                        "(Sources & Uses).\n"
                        "2. Grow EBITDA and pay down debt over the hold.\n"
                        "3. Exit equity = exit multiple × exit EBITDA − remaining debt.\n"
                        "4. MOIC = exit equity ÷ entry equity; approximate IRR (~2.5× over 5 yrs ≈ 20%)."
                    ),
                    "key_takeaways": [
                        "LBO = buy with debt; leverage + debt paydown drive equity returns.",
                        "MOIC = exit equity ÷ entry equity; pair it with IRR.",
                        "Paper LBO: entry EV → debt/equity split → grow & pay down → exit → MOIC.",
                    ],
                },
                {
                    "slug": "fpa-and-fit",
                    "title": "The FP&A twist and fit questions",
                    "source_refs": "CFI (FP&A); Mergers & Inquisitions",
                    "body_md": (
                        "**FP&A** (internal, forward-looking) de-emphasizes deal mechanics and emphasizes:\n\n"
                        "- **Variance analysis** — actuals vs budget, and *explaining the drivers*.\n"
                        "- **Budget vs forecast** — a budget is a static annual target; a forecast is "
                        "regularly updated, often rolling.\n"
                        "- **Business partnering** — translating finance for operating teams.\n\n"
                        "**Fit decides close calls.** Because finalists are technically comparable, prepare "
                        "tight answers to:\n"
                        "- *\"Walk me through your resume\"* — a 60–90s narrative with a through-line.\n"
                        "- *\"Why investment banking / finance?\"* — the learning curve and deal exposure, "
                        "**not** money or prestige.\n"
                        "- *\"Why our firm?\"* — firm-specific: a group, deal flow, people you've met.\n"
                        "- *\"Walk me through a recent deal / pitch me a stock\"* — have one of each ready "
                        "with a thesis.\n\n"
                        "Use the Behavioral track for the STAR stories the fit round draws on."
                    ),
                    "key_takeaways": [
                        "FP&A: variance analysis, budget vs forecast, business partnering.",
                        "Have a tight resume walk-through and a 'why this firm' that's specific.",
                        "Prepare one recent deal and one stock pitch with a clear thesis.",
                    ],
                },
            ],
        },
    ],
}
