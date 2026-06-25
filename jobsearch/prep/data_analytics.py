"""Data & Analytics interview prep — for data analyst / data scientist resumes
(the ``data`` discipline). Distilled from DataLemur / *Ace the Data Science
Interview*, Statistics By Jim, scikit-learn docs, and Kohavi/Tang/Xu,
*Trustworthy Online Controlled Experiments*.
"""

TRACK_DATA = {
    "slug": "data-analytics",
    "title": "Data & Analytics Interviews",
    "description": (
        "The analytics/data-science gauntlet: SQL screens, statistics & "
        "probability, A/B testing, product-sense metrics, and ML concepts. "
        "Complements the software tracks for data roles."
    ),
    "disciplines": ["data"],
    "modules": [
        {
            "slug": "data-sql-stats",
            "title": "SQL & Statistics",
            "summary": "Window functions, joins, and GROUP BY; hypothesis testing, p-values, and error types.",
            "source_refs": "DataLemur; Statistics By Jim",
            "est_minutes": 35,
            "lessons": [
                {
                    "slug": "sql-screen",
                    "title": "The SQL screen",
                    "source_refs": "DataLemur",
                    "body_md": (
                        "SQL screens test shaping data under time pressure. The most-tested topics:\n\n"
                        "- **Joins** — INNER vs LEFT/RIGHT/FULL.\n"
                        "- **GROUP BY / aggregations** — `WHERE` filters rows *before* grouping; `HAVING` "
                        "filters groups *after*.\n"
                        "- **Window functions** (the top advanced topic) — `ROW_NUMBER` / `RANK` / "
                        "`DENSE_RANK`, running totals, `LAG` / `LEAD`.\n"
                        "- **CTEs / subqueries** and **date manipulation**.\n\n"
                        "*Example — 2nd-highest salary per department:* use "
                        "`DENSE_RANK() OVER (PARTITION BY dept ORDER BY salary DESC)` in a CTE, filter "
                        "`rnk = 2`. Know the ranking distinction: for 100, 100, 90 → ROW_NUMBER = 1,2,3; "
                        "RANK = 1,1,3; DENSE_RANK = 1,1,2.\n\n"
                        "*Running total:* "
                        "`SUM(rev) OVER (ORDER BY d ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)`."
                    ),
                    "key_takeaways": [
                        "Window functions are the most-tested advanced SQL — drill RANK vs DENSE_RANK vs ROW_NUMBER.",
                        "WHERE filters rows before grouping; HAVING filters groups after.",
                        "Reach for a CTE + window function for 'Nth per group' questions.",
                    ],
                },
                {
                    "slug": "stats-probability",
                    "title": "Statistics & probability",
                    "source_refs": "Statistics By Jim",
                    "body_md": (
                        "Core concepts, in the phrasings interviewers probe:\n\n"
                        "- **Hypothesis testing:** state H₀ (\"no effect\") and H₁; compute a test statistic "
                        "and p-value; reject H₀ if p < α.\n"
                        "- **p-value (get this exactly right):** the probability of a result at least as "
                        "extreme as observed *assuming the null is true*. It is **not** the probability the "
                        "null is true.\n"
                        "- **Type I / II:** Type I = false positive (reject a true null) = α; Type II = "
                        "false negative (fail to reject a false null) = β. **Power = 1 − β** (target ~80%).\n"
                        "- Also: confidence intervals, the Central Limit Theorem, Bayes' theorem, and the "
                        "bias–variance trade-off.\n\n"
                        "*Explain a p-value to a stakeholder:* \"If the feature truly did nothing, the "
                        "p-value is the chance we'd see a result this big by luck; under 5% means luck is "
                        "unlikely. It does NOT mean a 95% chance the feature works.\""
                    ),
                    "key_takeaways": [
                        "A p-value assumes the null is true — it is not P(null is true).",
                        "Type I = false positive (α); Type II = false negative (β); power = 1 − β.",
                        "Be able to explain significance in plain language to a non-technical stakeholder.",
                    ],
                },
            ],
        },
        {
            "slug": "data-experiments-ml",
            "title": "A/B Testing & ML Concepts",
            "summary": "Designing and reading experiments, plus the ML fundamentals (overfitting, precision/recall).",
            "source_refs": "Kohavi/Tang/Xu; scikit-learn",
            "est_minutes": 30,
            "lessons": [
                {
                    "slug": "ab-testing",
                    "title": "A/B testing end-to-end",
                    "source_refs": "Kohavi/Tang/Xu, Trustworthy Online Controlled Experiments",
                    "body_md": (
                        "**Design:** hypothesis → randomization unit (usually the user) → **OEC** (the "
                        "primary success metric, tied to long-term value) → guardrail/invariant metrics → "
                        "sample size & power (from 80% power, α = 5%, baseline, and the minimum detectable "
                        "effect). Run for ≥ 1–2 full business cycles.\n\n"
                        "**Pitfalls:** *peeking* (inflates false positives), *novelty/primacy effects*, "
                        "*network effects* (use cluster/geo randomization), *multiple comparisons* "
                        "(Bonferroni), and *Simpson's paradox*.\n\n"
                        "**Reading results:** check the sample-ratio mismatch and guardrails *first*, then "
                        "look at both statistical significance **and** the practical effect size."
                    ),
                    "key_takeaways": [
                        "Define the OEC and guardrail metrics, and size the test for ~80% power before launch.",
                        "Don't peek; watch for novelty, network effects, and Simpson's paradox.",
                        "Judge results on significance AND practical effect size, after checking guardrails.",
                    ],
                },
                {
                    "slug": "ml-concepts",
                    "title": "ML concepts & evaluation",
                    "source_refs": "scikit-learn",
                    "body_md": (
                        "- **Supervised vs unsupervised** (k-means, PCA); train/validation/test split + "
                        "cross-validation.\n"
                        "- **Overfitting** (great on train, poor on unseen) — prevent with CV, more data, "
                        "simpler models, early stopping, and **regularization** (L1/Lasso → sparsity/feature "
                        "selection; L2/Ridge → smooth shrinkage).\n"
                        "- **Bias–variance:** bagging/Random Forest ↓ variance; boosting/XGBoost ↓ bias.\n"
                        "- **Evaluation:** **precision = TP/(TP+FP)**, **recall = TP/(TP+FN)**, **F1** = "
                        "harmonic mean; ROC-AUC (PR-AUC for imbalanced data); RMSE for regression.\n\n"
                        "*Precision vs recall:* optimize **precision** when false positives are costly (spam "
                        "filter); **recall** when false negatives are costly (cancer/fraud detection); F1 "
                        "when both matter. For an **analytics case**, structure it like any case: clarify → "
                        "assumptions → issue tree → analyze (cohort/segmentation/A-B) → recommend with caveats."
                    ),
                    "key_takeaways": [
                        "Prevent overfitting with cross-validation, regularization, and simpler models.",
                        "precision = TP/(TP+FP); recall = TP/(TP+FN); F1 balances both.",
                        "Optimize precision when false positives hurt, recall when false negatives hurt.",
                    ],
                },
            ],
        },
    ],
}
