"""Marketing interview prep — for marketing and editorial/content resumes (the
``marketing`` discipline). Distilled from HubSpot (GTM, CAC), Reforge (growth
loops), April Dunford (positioning), and HBS Online (LTV:CAC).
"""

TRACK_MARKETING = {
    "slug": "marketing",
    "title": "Marketing Interviews",
    "description": (
        "Portfolio/campaign walkthroughs, the marketing case (build a GTM plan, "
        "grow a funnel), and the metrics that matter — CAC, LTV, ROAS, and the "
        "LTV:CAC ratio. For marketing, growth, brand, and content roles."
    ),
    "disciplines": ["marketing"],
    "modules": [
        {
            "slug": "marketing-frameworks",
            "title": "Funnels, GTM & Positioning",
            "summary": "The marketing funnel, a GTM-plan structure, and positioning against alternatives.",
            "source_refs": "HubSpot (GTM); April Dunford; Reforge",
            "est_minutes": 25,
            "lessons": [
                {
                    "slug": "funnel-gtm",
                    "title": "The funnel, GTM plans & growth loops",
                    "source_refs": "HubSpot (GTM); Reforge",
                    "body_md": (
                        "**The marketing funnel:** Awareness → Consideration → Conversion → Retention → "
                        "Advocacy (growth teams use **AARRR**). **Growth loops** differ from funnels: a "
                        "loop reinvests its output back into its input so growth compounds, rather than "
                        "running linearly.\n\n"
                        "**A GTM-plan structure** (the most common case — *\"launch product X\"* / *\"grow "
                        "signups 20%\"*):\n"
                        "1. Market & segmentation.\n"
                        "2. Target customer (ICP) & personas.\n"
                        "3. Positioning & messaging.\n"
                        "4. Pricing & packaging.\n"
                        "5. Channels & sales motion.\n"
                        "6. Launch plan.\n"
                        "7. Goals & metrics.\n\n"
                        "Supporting models: **STP** (Segmentation, Targeting, Positioning) and the **4 Ps** "
                        "(Product, Price, Place, Promotion)."
                    ),
                    "key_takeaways": [
                        "Know the funnel (AARRR) and how growth loops compound vs linear funnels.",
                        "Structure a GTM plan: market → ICP → positioning → pricing → channels → launch → metrics.",
                        "STP and the 4 Ps are reliable supporting scaffolds.",
                    ],
                },
                {
                    "slug": "positioning",
                    "title": "Positioning (April Dunford)",
                    "source_refs": "April Dunford, Obviously Awesome",
                    "body_md": (
                        "Positioning defines how your product is the *best* at delivering something a "
                        "specific market cares about. April Dunford's components:\n\n"
                        "1. **Competitive alternatives** — what customers would use instead.\n"
                        "2. **Differentiated capabilities** — what you have that they don't.\n"
                        "3. **Value** those capabilities enable.\n"
                        "4. **Target customers** who care most about that value.\n"
                        "5. **Market category** you frame yourself within.\n\n"
                        "In brand/product-marketing rounds (which often end in a presentation), strong "
                        "candidates position *against alternatives* and tie every message back to customer "
                        "value — not feature lists."
                    ),
                    "key_takeaways": [
                        "Positioning = best at delivering value a specific segment cares about.",
                        "Define yourself against the customer's real alternatives.",
                        "Tie messaging to value, not feature lists.",
                    ],
                },
            ],
        },
        {
            "slug": "marketing-metrics",
            "title": "Metrics & the Portfolio Walkthrough",
            "summary": "CAC, LTV, the LTV:CAC rule of thumb, ROAS, and how to present a campaign.",
            "source_refs": "HubSpot (CAC); HBS Online (LTV:CAC)",
            "est_minutes": 25,
            "lessons": [
                {
                    "slug": "marketing-metrics-formulas",
                    "title": "The core metrics (with formulas)",
                    "source_refs": "HBS Online; Geckoboard",
                    "body_md": (
                        "- **CAC** = total sales & marketing cost ÷ new customers.\n"
                        "- **LTV / CLV** = ARPU × average lifespan (often margin-adjusted).\n"
                        "- **LTV:CAC** = LTV ÷ CAC; **~3:1 is the healthy rule of thumb** (below ~1:1 is "
                        "unsustainable; above ~5:1 often means *under*-investing in growth).\n"
                        "- **ROAS** = ad revenue ÷ ad spend; **MER** = total revenue ÷ total marketing spend.\n"
                        "- **CTR** = clicks ÷ impressions; **CPC / CPM** = cost per click / per 1,000 "
                        "impressions.\n"
                        "- **CAC payback** = CAC ÷ (monthly revenue per customer × gross margin %).\n\n"
                        "*Case:* \"CAC is rising and conversion is falling — what do you do?\" → segment by "
                        "source/geo/device, check tracking, map funnel drop-offs, and fix while finding the "
                        "root cause. \"Which channels would you test?\" → start with 1–2, define success by "
                        "**payback**, then double down on winners."
                    ),
                    "key_takeaways": [
                        "LTV:CAC ~3:1 is healthy; <1:1 unsustainable, >5:1 likely under-investing.",
                        "CAC = S&M spend ÷ new customers; ROAS = ad revenue ÷ ad spend.",
                        "Judge channel tests by CAC payback, then scale winners.",
                    ],
                },
                {
                    "slug": "portfolio-walkthrough",
                    "title": "The portfolio / campaign walkthrough",
                    "source_refs": "Synthesis (HubSpot + STAR)",
                    "body_md": (
                        "Most loops open with *\"walk me through your most successful campaign.\"* Use "
                        "**STAR** and always close with **quantified results + what you'd change**:\n\n"
                        "- **Situation/Task** — the goal and the constraint (budget, timeline, audience).\n"
                        "- **Action** — your strategy: targeting, channels, creative, the test plan.\n"
                        "- **Result** — the numbers (pipeline, conversion lift, ROAS, CAC), then the lesson.\n\n"
                        "Role nuance: *brand/product marketing* is judged on positioning and messaging; "
                        "*growth/performance* on quantitative rigor (experiments, channel economics, even "
                        "SQL); *content/demand-gen* on the funnel and lead quality (MQL→SQL). Tailor which "
                        "campaign you lead with to the role."
                    ),
                    "key_takeaways": [
                        "Walk campaigns through STAR; always end with metrics and a lesson.",
                        "Lead with a campaign that matches the role's flavor (brand vs growth vs content).",
                        "Quantify impact: pipeline, conversion lift, ROAS, or CAC.",
                    ],
                },
            ],
        },
    ],
}
