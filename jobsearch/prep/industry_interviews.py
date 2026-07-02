"""Industry-specific interview prep for fields whose loops are mostly behavioral
+ scenario rather than a named technical format: healthcare/nursing, legal,
education/teaching, and HR/recruiting (the ``healthcare``, ``legal``,
``education``, and ``hr`` disciplines).

Across all of these, **STAR** (see the Behavioral track) is the near-universal
answer framework; each lesson adds the domain-specific scenarios and the one or
two technical fundamentals interviewers expect. Sources are cited per lesson
(Nurse.org, Chambers Student, We Are Teachers, SHRM/AIHR).
"""

TRACK_INDUSTRY = {
    "slug": "industry-interviews",
    "title": "Industry-Specific Interviews",
    "description": (
        "Behavioral + scenario interview prep for healthcare/nursing, legal, "
        "education/teaching, and HR/recruiting — the fields whose interviews "
        "are competency- and scenario-driven. Pair with the Behavioral track."
    ),
    "disciplines": ["healthcare", "legal", "education", "hr"],
    "modules": [
        {
            "slug": "clinical-legal",
            "title": "Healthcare & Legal",
            "summary": "Clinical scenario/prioritization interviews and legal competency + commercial-awareness interviews.",
            "source_refs": "Nurse.org; Chambers Student",
            "est_minutes": 25,
            "lessons": [
                {
                    "slug": "healthcare-nursing",
                    "title": "Healthcare & nursing interviews",
                    "source_refs": "Nurse.org",
                    "body_md": (
                        "**Format:** behavioral + **situational clinical scenarios** built on patient "
                        "safety, prioritization, and communication. A common variant asks you to **triage "
                        "3–4 hypothetical patients**.\n\n"
                        "**Framework:** STAR for behavioral, plus a clinical prioritization model — "
                        "**ABC / ABCDE** (Airway, Breathing, Circulation, Disability, Exposure) — to walk "
                        "through who you'd see first and why.\n\n"
                        "**Typical questions:**\n"
                        "- \"You have multiple critical patients — how do you prioritize?\" (use ABCDE, "
                        "escalate, delegate).\n"
                        "- \"Tell me about a time you dealt with a difficult patient or family.\"\n"
                        "- \"Tell me about a time you disagreed with a physician's order.\" (patient "
                        "safety first; escalate through the chain respectfully).\n\n"
                        "Emphasize patient safety, clear communication, and teamwork in every answer."
                    ),
                    "key_takeaways": [
                        "Expect clinical scenarios and patient-triage questions, answered with ABCDE.",
                        "Use STAR for behavioral; lead every answer with patient safety.",
                        "For disagreements, show respectful escalation, not confrontation.",
                    ],
                },
                {
                    "slug": "legal-interviews",
                    "title": "Legal interviews (associate / counsel)",
                    "source_refs": "Chambers Student",
                    "body_md": (
                        "**Format:** competency/behavioral + \"fit\" + heavy **commercial awareness**; often "
                        "an assessment centre (group exercise, written exercise, presentation, interview).\n\n"
                        "**Framework:** STAR for competencies, plus **commercial awareness** — be ready to "
                        "discuss a recent deal or news story and its implications for the client *and* the "
                        "firm.\n\n"
                        "**Typical questions:**\n"
                        "- \"Why this practice area, and why this firm?\" (specific, researched reasons).\n"
                        "- \"Tell me about a recent deal or news story and its commercial implications.\"\n"
                        "- \"Tell me about a time you handled competing deadlines / managed a heavy "
                        "workload.\"\n\n"
                        "Firms screen for judgment, attention to detail, resilience, and genuine interest in "
                        "*their* clients and sectors — not generic enthusiasm for the law."
                    ),
                    "key_takeaways": [
                        "Commercial awareness is the differentiator — follow deals and the business press.",
                        "Have specific, researched reasons for the practice area and the firm.",
                        "Use STAR for competencies; expect an assessment centre, not just a chat.",
                    ],
                },
            ],
        },
        {
            "slug": "education-hr",
            "title": "Teaching & HR / Recruiting",
            "summary": "Teaching demo lessons + classroom-management scenarios, and HR/recruiting judgment + metrics.",
            "source_refs": "We Are Teachers; SHRM; AIHR",
            "est_minutes": 25,
            "lessons": [
                {
                    "slug": "teaching-interviews",
                    "title": "Teaching interviews (K-12)",
                    "source_refs": "We Are Teachers",
                    "body_md": (
                        "**Format:** behavioral + scenario (classroom management, differentiation, parent "
                        "communication) + often a **demo lesson** + your philosophy of education.\n\n"
                        "**Frameworks:** **\"I do / we do / you do\"** (gradual release) for the demo; "
                        "**UDL** (Universal Design for Learning) for differentiation; STAR for behavioral.\n\n"
                        "**Typical questions:**\n"
                        "- \"How do you handle a disruptive student / your classroom-management approach?\" "
                        "(favor *proactive/preventive* answers over punitive ones).\n"
                        "- \"How do you differentiate for diverse learners (ELLs, students with "
                        "disabilities)?\"\n"
                        "- \"What is your philosophy of education?\"\n\n"
                        "Ground answers in concrete routines, data on student outcomes, and inclusion."
                    ),
                    "key_takeaways": [
                        "Be ready for a demo lesson — structure it 'I do / we do / you do.'",
                        "Classroom-management answers should be proactive, not punitive.",
                        "Show differentiation (UDL) and use student-outcome data.",
                    ],
                },
                {
                    "slug": "hr-recruiting",
                    "title": "HR & recruiting interviews",
                    "source_refs": "SHRM; AIHR",
                    "body_md": (
                        "**Format:** behavioral + situational (employee relations, confidentiality, "
                        "conflict, judgment). Recruiters also get **metrics-driven** questions.\n\n"
                        "**Framework:** STAR; for recruiters, fluency in recruiting metrics — time-to-fill, "
                        "quality of hire, offer-acceptance rate, source-of-hire.\n\n"
                        "**Typical questions:**\n"
                        "- \"How do you handle a conflict between two employees?\"\n"
                        "- \"Tell me about a time you handled confidential or sensitive information.\"\n"
                        "- *(recruiters)* \"How do you source passive candidates?\" / \"What's a healthy "
                        "time-to-fill, and how do you build pipeline?\"\n\n"
                        "Show discretion, fairness, and an evidence-based, metrics-aware approach to people "
                        "decisions."
                    ),
                    "key_takeaways": [
                        "Expect employee-relations and confidentiality scenarios — show discretion and fairness.",
                        "Recruiters: know time-to-fill, quality of hire, and sourcing strategy.",
                        "Answer with STAR and an evidence-based, metrics-aware lens.",
                    ],
                },
            ],
        },
    ],
}
