"""Behavioral Interviews — a universal prep track.

Behavioral ("tell me about a time…") interviews are used in essentially every
industry, so this track carries the ``general`` discipline and is recommended
for every resume. Content distilled from: McDowell, *Cracking the Coding
Interview* 6e, ch. 5 (Nugget-First + S.A.R., the Interview Preparation Grid);
DDI's Targeted Selection (the 1974 origin of STAR); Google re:Work structured
interviewing; Amazon's published Leadership Principles + Bar Raiser process;
and university career-center guidance (MIT CAPD, Harvard FAS). Each lesson
cites its sources.
"""

TRACK_BEHAVIORAL = {
    "slug": "behavioral",
    "title": "Behavioral Interviews",
    "description": (
        "The interview every industry runs. Learn why behavioral interviews "
        "predict hiring decisions, how answers are scored, the STAR / Nugget-"
        "First frameworks, how to build a reusable story bank, a 50+ question "
        "bank by competency, and how to handle 'tell me about yourself,' "
        "weaknesses, and salary. Universal — recommended for every resume."
    ),
    "disciplines": ["general"],
    "modules": [
        # ----------------------------------------------------------- B.1
        {
            "slug": "behavioral-foundations",
            "title": "Why Behavioral Interviews Exist & How They're Scored",
            "summary": (
                "The premise that past behavior predicts future behavior, "
                "competency-based hiring, and the specific signals interviewers "
                "score: specificity, 'I' vs 'we', outcomes, and reflection."
            ),
            "source_refs": "Google re:Work; DDI Targeted Selection",
            "est_minutes": 25,
            "lessons": [
                {
                    "slug": "why-behavioral",
                    "title": "Why behavioral questions predict hiring",
                    "source_refs": "Google re:Work; DDI",
                    "body_md": (
                        "Behavioral interviewing rests on one research-backed premise: **past "
                        "behavior is the best available predictor of future behavior.** That is why "
                        "the questions almost always open with *\"Tell me about a time when…\"*, "
                        "*\"Give me an example of…\"*, or *\"Describe a situation where…\"* rather than "
                        "the hypothetical *\"What would you do if…?\"* Hypotheticals reveal how you "
                        "*think*; behavioral questions reveal what you have actually *done*.\n\n"
                        "Google's People Analytics team (published through **re:Work**) found that "
                        "**structured** behavioral interviewing has materially higher predictive "
                        "validity — and *less* bias — than unstructured conversation, which is why "
                        "Google standardized it company-wide.\n\n"
                        "Behavioral interviews are the delivery mechanism for **competency-based "
                        "hiring**. The employer first defines the competencies that predict success "
                        "in the role (leadership, collaboration, dealing with ambiguity, customer "
                        "focus, ownership…), then writes questions to elicit evidence of each. In a "
                        "structured loop each interviewer is assigned a subset of competencies so the "
                        "panel collectively covers them all, and answers are scored against a "
                        "**standardized rubric**.\n\n"
                        "> The mental model that changes everything: **you are not having a "
                        "conversation; you are supplying evidence against a scorecard.**"
                    ),
                    "key_takeaways": [
                        "Behavioral questions ask what you *did*, not what you *would* do.",
                        "Structured interviewing predicts performance better and reduces bias (Google re:Work).",
                        "Each interviewer scores specific competencies against a rubric — give them evidence.",
                    ],
                },
                {
                    "slug": "how-scored",
                    "title": "The four signals every answer is graded on",
                    "source_refs": "DDI; The Muse; Big Interview",
                    "body_md": (
                        "Interviewers (and rubrics) look for specific **signal**. A pleasant story "
                        "that lacks these scores low even if it *sounds* good:\n\n"
                        "1. **Specificity.** One concrete, real event with details — not *\"I always…\"* "
                        "or *\"I usually…\"*. Generalities register as *no signal*.\n"
                        "2. **\"I\" vs \"we\".** The interviewer is hiring *you*, not your team. Answers "
                        "drowned in *\"we did X\"* make your individual contribution unscoreable. Foreground "
                        "your own decisions and actions.\n"
                        "3. **Outcomes & metrics.** Quantified results (*\"cut processing time 30%\"*, "
                        "*\"raised NPS 12 points\"*, *\"delivered two weeks early\"*) prove impact. *\"It went "
                        "well\"* is unscoreable.\n"
                        "4. **Reflection / learning.** Especially on failure questions, evidence that you "
                        "extracted a lesson and changed your behavior signals growth and coachability.\n\n"
                        "Candidates lose offers not because their experiences are weak but because their "
                        "answers supply no scoreable signal. Before the interview, pressure-test each story: "
                        "*Is it one specific event? Is it about me? Is there a number? Did I learn something?*"
                    ),
                    "key_takeaways": [
                        "Pick one real event — generalities score as no signal.",
                        "Lead with 'I'; reserve 'we' for context only.",
                        "Quantify the result, and close with what you learned.",
                    ],
                },
            ],
        },
        # ----------------------------------------------------------- B.2
        {
            "slug": "behavioral-frameworks",
            "title": "Answer Frameworks: STAR, Variants & Nugget-First",
            "summary": (
                "STAR (Situation, Task, Action, Result) and its origin, the "
                "variants that add reflection (CARL, PARLA), McDowell's "
                "Nugget-First + S.A.R., and the #1 mistake: too little Action."
            ),
            "source_refs": "DDI; CtCI ch. 5; MIT CAPD",
            "est_minutes": 30,
            "lessons": [
                {
                    "slug": "star-method",
                    "title": "STAR, and why Action is ~60% of the answer",
                    "source_refs": "DDI (Targeted Selection, 1974); MIT CAPD",
                    "body_md": (
                        "**STAR = Situation, Task, Action, Result.** It was created by **Development "
                        "Dimensions International (DDI) in 1974** as part of its *Targeted Selection®* "
                        "system and is now the most widely taught structure worldwide.\n\n"
                        "| Beat | What it is | Time budget |\n"
                        "|------|-----------|-------------|\n"
                        "| **Situation** | The context: where, when, what was going on. *Brief.* | ~20% |\n"
                        "| **Task** | Your specific responsibility or the goal you owned. | ~10% |\n"
                        "| **Action** | What **you personally** did, step by step, and why. | **~60%** |\n"
                        "| **Result** | The outcome — quantified — plus what you learned. | ~10% |\n\n"
                        "MIT's career office recommends roughly **S 20% / T 10% / A 60% / R 10%**. "
                        "McDowell makes the same point in *Cracking the Coding Interview*: in her S.A.R. "
                        "structure the **Action should be about half the answer**, because the action is "
                        "where *your* signal lives. If you spend 90 seconds setting the scene and 15 "
                        "seconds on what you did, you've given the interviewer nothing to score."
                    ),
                    "key_takeaways": [
                        "STAR = Situation, Task, Action, Result (DDI, 1974).",
                        "Spend ~60% of the answer on your Action — it carries the signal.",
                        "Keep Situation/Task brief; always land a quantified Result.",
                    ],
                },
                {
                    "slug": "framework-variants",
                    "title": "Variants that add reflection: CAR, CARL, PARLA, SOAR",
                    "source_refs": "Resumeble; The Interview Guys",
                    "body_md": (
                        "STAR is the default, but several variants tighten it or add an explicit "
                        "**learning** beat — valuable for *failure*, *feedback*, and *adaptability* "
                        "questions:\n\n"
                        "| Framework | Stands for | Adds / best for |\n"
                        "|-----------|-----------|------------------|\n"
                        "| **SAR** | Situation, Action, Result | STAR minus Task; tighter. |\n"
                        "| **CAR / PAR** | Challenge (Problem), Action, Result | Faster; leads with the problem. |\n"
                        "| **CARL** | Context, Action, Result, **Learning** | Explicit reflection. |\n"
                        "| **SOAR** | Situation, Obstacle, Action, Result | Foregrounds the obstacle — good for leadership. |\n"
                        "| **PARLA** | Problem, Action, Result, **Learning, Application** | Lesson **and** how you applied it later. |\n\n"
                        "**To add reflection to any framework**, append one or two sentences after the "
                        "Result: *\"What I took away was X, and I've since applied it by doing Y.\"* That "
                        "converts a flat success story into evidence of self-awareness and growth — the "
                        "exact signal failure and feedback questions are scored on."
                    ),
                    "key_takeaways": [
                        "Use SAR/CAR to tighten; CARL/PARLA to add a learning beat.",
                        "End reflective answers with 'what I learned, and how I applied it.'",
                        "Pick the variant that fits the question — don't force STAR onto a failure story.",
                    ],
                },
                {
                    "slug": "nugget-first",
                    "title": "McDowell's Nugget-First + S.A.R.",
                    "source_refs": "CtCI 6e, ch. 5",
                    "body_md": (
                        "*Cracking the Coding Interview* (ch. 5) recommends two structures used "
                        "**together**:\n\n"
                        "- **Nugget First** — open with a one-sentence headline of the story *before* you "
                        "tell it: *\"That's actually how I ended up rebuilding our deployment pipeline over "
                        "a single weekend.\"* The nugget grabs attention, frames the story, and means that "
                        "even if you're interrupted the interviewer already has the point.\n"
                        "- **S.A.R.** — then deliver Situation → Action → Result, with **Action ~50%**.\n\n"
                        "Combined: **Nugget → Situation → Action → Result.** McDowell's supporting rules:\n\n"
                        "- **Be specific, not arrogant.** Concrete details, not self-labels.\n"
                        "- **Limit detail.** Give the minimum needed — *\"if the interviewer wants more, "
                        "they'll ask.\"*\n"
                        "- **Focus on yourself, not the team.** Convert *\"we decided\"* into *\"I proposed, and "
                        "the team agreed.\"*"
                    ),
                    "key_takeaways": [
                        "Open with a one-sentence 'nugget' that headlines the story.",
                        "Be specific, limit detail, and keep the focus on you (CtCI ch. 5).",
                        "Nugget → Situation → Action → Result is a reliable default.",
                    ],
                },
            ],
        },
        # ----------------------------------------------------------- B.3
        {
            "slug": "behavioral-story-bank",
            "title": "Building Your Story Bank",
            "summary": (
                "Prepare 8-12 flexible stories that flex to many questions, and "
                "map them to competencies with McDowell's Interview Preparation Grid."
            ),
            "source_refs": "CtCI ch. 5; The Muse",
            "est_minutes": 25,
            "lessons": [
                {
                    "slug": "story-bank",
                    "title": "8-12 stories that flex to many questions",
                    "source_refs": "The Muse; Big Interview",
                    "body_md": (
                        "You can't script an answer to every possible question — there are hundreds. "
                        "Instead, prepare a **finite bank of stories that flex.** The same *\"I turned "
                        "around a failing project\"* story can answer leadership, ambiguity, "
                        "prioritization, *and* greatest-accomplishment questions, depending on which beat "
                        "you emphasize.\n\n"
                        "**How many?** The consensus is **8–12 strong stories**. Since most behavioral "
                        "interviews contain only **4–6 questions**, a bank of ~10 lets you pick the "
                        "best-fit story and never repeat yourself.\n\n"
                        "**Choose** your most significant, *true*, detail-rich experiences — projects you "
                        "led, problems you solved, conflicts you navigated, failures you owned, things you "
                        "built or changed. Prioritize stories that are recent, high-impact/quantifiable, "
                        "and rich enough to retell from multiple angles.\n\n"
                        "**Coverage rule:** make sure every core competency is covered by **at least two** "
                        "stories, so you're never stuck reusing one story twice in the same loop. Rehearse "
                        "each aloud to ~2 minutes with the nugget and the metric memorized — rehearse the "
                        "*beats*, not a word-for-word script (scripts sound robotic and crumble when probed)."
                    ),
                    "key_takeaways": [
                        "Prepare ~8-12 versatile stories, not one answer per question.",
                        "Cover every competency with at least two stories.",
                        "Rehearse beats and metrics aloud — never a verbatim script.",
                    ],
                },
                {
                    "slug": "prep-grid",
                    "title": "The Interview Preparation Grid",
                    "source_refs": "CtCI 6e, ch. 5",
                    "body_md": (
                        "McDowell's **Interview Preparation Grid** is the canonical tool for building the "
                        "bank. It's a matrix:\n\n"
                        "- **Columns = the major items on your resume** — each project, job, internship, or "
                        "significant activity.\n"
                        "- **Rows = the recurring prompts** — *most challenging, what you learned, most "
                        "enjoyable, hardest problem, what you'd do differently, conflict with a teammate, "
                        "biggest accomplishment.*\n"
                        "- **Each cell** holds a 1–2 word reminder of a story.\n\n"
                        "Filled in, the grid shows at a glance which experiences are versatile and where "
                        "you have gaps. Add a second axis — a **competency tag** per story — so you can see "
                        "coverage:\n\n"
                        "| Story | S/T/A/R bullets | Quantified result | Competencies |\n"
                        "|-------|-----------------|-------------------|--------------|\n"
                        "| Rescued the Q3 launch | … | shipped 2 wks early, +18% adoption | Leadership, Ambiguity, Ownership |\n"
                        "| The prod bug I caused | … | outage 40→4 min, added tests | Failure, Ownership, Integrity |\n"
                        "| Convinced legal to sign off | … | unblocked a $2M deal | Influence, Communication |\n"
                    ),
                    "key_takeaways": [
                        "Build a grid: resume items × common prompts, one story per cell.",
                        "Tag each story with the competencies it demonstrates.",
                        "The grid exposes versatile stories and coverage gaps at a glance.",
                    ],
                },
            ],
        },
        # ----------------------------------------------------------- B.4
        {
            "slug": "behavioral-question-bank",
            "title": "The Question Bank by Competency",
            "summary": (
                "50+ canonical behavioral questions grouped by competency — "
                "leadership, teamwork, conflict, failure, ambiguity, influence, "
                "prioritization, ownership, customer focus, feedback, ethics."
            ),
            "source_refs": "The Muse; Harvard HMS; Amazon LP sets",
            "est_minutes": 30,
            "lessons": [
                {
                    "slug": "questions-core-competencies",
                    "title": "Leadership, teamwork, conflict, failure, ambiguity",
                    "source_refs": "The Muse; Harvard HMS HR",
                    "body_md": (
                        "Map each cluster to two stories from your bank.\n\n"
                        "**Leadership**\n"
                        "- Tell me about a time you led a team to accomplish a goal.\n"
                        "- Describe a time you stepped up to lead when you weren't asked.\n"
                        "- Tell me about a time you had to make an unpopular decision.\n\n"
                        "**Teamwork / Collaboration**\n"
                        "- Tell me about a time you worked effectively as part of a team.\n"
                        "- Describe working with someone whose style was very different from yours.\n"
                        "- Give an example of helping a struggling teammate.\n\n"
                        "**Conflict**\n"
                        "- Tell me about a conflict with a coworker and how you resolved it.\n"
                        "- Describe a disagreement with your manager.\n"
                        "- Tell me about a time you gave someone difficult feedback.\n\n"
                        "**Failure / Mistakes**\n"
                        "- Tell me about a time you failed. What did you learn?\n"
                        "- Describe a mistake you made and how you handled it.\n"
                        "- Tell me about a time a project didn't go as planned.\n\n"
                        "**Dealing with Ambiguity**\n"
                        "- Tell me about a decision you made without all the information.\n"
                        "- Describe a situation where priorities kept changing.\n"
                        "- Tell me about taking on something completely new or unfamiliar."
                    ),
                    "key_takeaways": [
                        "Prepare 2 stories each for leadership, teamwork, conflict, failure, ambiguity.",
                        "Failure questions are really about reflection and growth.",
                        "Conflict questions test maturity — show resolution, not blame.",
                    ],
                },
                {
                    "slug": "questions-influence-ownership",
                    "title": "Influence, prioritization, ownership, customer, feedback, ethics",
                    "source_refs": "The Muse; Big Interview",
                    "body_md": (
                        "**Influence / Persuasion without authority**\n"
                        "- Tell me about a time you convinced someone to see things your way.\n"
                        "- Describe influencing a decision without formal authority.\n"
                        "- Tell me about using data to win an argument.\n\n"
                        "**Prioritization / Time management**\n"
                        "- Tell me about juggling multiple competing priorities.\n"
                        "- Describe working under a tight deadline.\n"
                        "- Tell me about a time you had to say no or push back.\n\n"
                        "**Initiative / Ownership**\n"
                        "- Tell me about going above and beyond what was required.\n"
                        "- Describe identifying a problem and fixing it before being asked.\n"
                        "- Give an example of a process you improved.\n\n"
                        "**Customer focus**\n"
                        "- Tell me about going out of your way for a customer.\n"
                        "- Describe using customer feedback to improve something.\n"
                        "- Tell me about handling an unhappy or difficult customer.\n\n"
                        "**Handling feedback / criticism**\n"
                        "- Tell me about receiving critical feedback and how you responded.\n"
                        "- Describe changing your approach based on feedback.\n\n"
                        "**Adaptability & Ethics**\n"
                        "- Tell me about adapting to a significant change at work.\n"
                        "- Tell me about an ethical dilemma and how you handled it."
                    ),
                    "key_takeaways": [
                        "Influence-without-authority is a top signal — prepare a data-driven persuasion story.",
                        "Ownership questions reward fixing things nobody asked you to fix.",
                        "For ethics/feedback, show the principle and the behavior change.",
                    ],
                },
                {
                    "slug": "questions-signature",
                    "title": "Signature questions every loop asks",
                    "source_refs": "The Muse; Indeed",
                    "body_md": (
                        "These appear in nearly every interview — prepare them explicitly:\n\n"
                        "- **Tell me about yourself.** (See the Special Questions module.)\n"
                        "- **What's your greatest accomplishment?** / Something you're proud of.\n"
                        "- **What's your greatest weakness?** (and greatest strength)\n"
                        "- **Why do you want to work here / for this role?**\n"
                        "- **Where do you see yourself in 5 years?**\n"
                        "- **Why are you leaving your current job?**\n"
                        "- **What are your salary expectations?**\n"
                        "- **Why should we hire you?**\n"
                        "- **Do you have any questions for us?** (Always have 2–3 ready.)\n\n"
                        "The last one is scored too: thoughtful questions about the team, the role's "
                        "challenges, or how success is measured signal genuine interest."
                    ),
                    "key_takeaways": [
                        "Rehearse the signature questions — they're guaranteed.",
                        "Always bring 2-3 questions to ask; it's part of the evaluation.",
                        "Frame 'why leaving' around what you're moving toward, not away from.",
                    ],
                },
            ],
        },
        # ----------------------------------------------------------- B.5
        {
            "slug": "competency-frameworks",
            "title": "Competency Frameworks: Amazon LPs & Structured Loops",
            "summary": (
                "The 16 Amazon Leadership Principles and the Bar Raiser process "
                "as the famous worked example, plus Google re:Work, McKinsey PEI, "
                "and how to map your stories to a framework."
            ),
            "source_refs": "Amazon Leadership Principles; Google re:Work",
            "est_minutes": 30,
            "lessons": [
                {
                    "slug": "amazon-lps",
                    "title": "Amazon's 16 Leadership Principles & the Bar Raiser",
                    "source_refs": "aboutamazon.com / amazon.jobs",
                    "body_md": (
                        "Amazon is the most transparent instance of competency-based behavioral "
                        "interviewing: its competencies are public, named, and woven into every interview. "
                        "Amazon has **16 Leadership Principles** (originally 14; the last two were added "
                        "July 1, 2021):\n\n"
                        "1. **Customer Obsession** — start from the customer and work backwards.\n"
                        "2. **Ownership** — think long-term; never *\"that's not my job.\"*\n"
                        "3. **Invent and Simplify** — seek new ideas; simplify.\n"
                        "4. **Are Right, A Lot** — strong judgment; seek to disconfirm your own beliefs.\n"
                        "5. **Learn and Be Curious** — never done learning.\n"
                        "6. **Hire and Develop the Best** — raise the bar with every hire.\n"
                        "7. **Insist on the Highest Standards** — continually raise the bar.\n"
                        "8. **Think Big** — bold direction inspires results.\n"
                        "9. **Bias for Action** — speed matters; many decisions are reversible.\n"
                        "10. **Frugality** — accomplish more with less.\n"
                        "11. **Earn Trust** — listen, speak candidly, be self-critical.\n"
                        "12. **Dive Deep** — stay connected to the details; audit frequently.\n"
                        "13. **Have Backbone; Disagree and Commit** — challenge respectfully, then commit.\n"
                        "14. **Deliver Results** — focus on key inputs and deliver with quality, on time.\n"
                        "15. **Strive to be Earth's Best Employer.**\n"
                        "16. **Success and Scale Bring Broad Responsibility.**\n\n"
                        "**The loop:** 4–5 back-to-back interviews; each interviewer owns 2–3 LPs. One is a "
                        "**Bar Raiser** — a trained interviewer from *outside* the hiring team with effective "
                        "**veto power**, asking not *\"Can they do the job?\"* but *\"Will they raise the bar?\"* "
                        "Everyone submits written, structured feedback and meets in a debrief the Bar Raiser "
                        "drives to an evidence-based consensus. Amazon explicitly coaches candidates to use "
                        "**STAR, lead with \"I,\" and quantify results.**"
                    ),
                    "key_takeaways": [
                        "Amazon scores against 16 named Leadership Principles; tag your stories to them.",
                        "The Bar Raiser is an external interviewer with veto — the bar is 'raise the team.'",
                        "Cover the high-frequency LPs: Customer Obsession, Ownership, Bias for Action, Dive Deep, Deliver Results.",
                    ],
                },
                {
                    "slug": "structured-interviews",
                    "title": "Google re:Work, McKinsey PEI & mapping stories to a framework",
                    "source_refs": "Google re:Work; Management Consulted (PEI)",
                    "body_md": (
                        "The Amazon mechanics are one case of a near-universal pattern: most large "
                        "employers run a **competency framework**.\n\n"
                        "- **Google** (re:Work) pioneered *structured interviewing*: every candidate gets the "
                        "**same vetted questions** (a mix of behavioral and situational), scored on "
                        "standardized rubrics. Google evaluates *General Cognitive Ability, Leadership* "
                        "(especially **emergent** leadership — stepping up *and* stepping back), "
                        "*Role-Related Knowledge,* and *\"Googleyness.\"*\n"
                        "- **McKinsey** runs a formal **Personal Experience Interview (PEI)** — a deep dive "
                        "into a single story, now probing **Leadership, Connection, Drive, and Growth.**\n"
                        "- The **UK Civil Service** interviews against published *Success Profiles* behaviours.\n\n"
                        "**What to do with this:** take your story bank and add a column for the target "
                        "company's framework (Amazon LPs, Google attributes, a PEI dimension). Tag each story "
                        "with every competency it hits, and aim to cover the framework with one or two strong "
                        "stories each. In the room, briefly *name the principle* when natural — it shows "
                        "fluency in their language."
                    ),
                    "key_takeaways": [
                        "Structured loops ask everyone the same rubric-scored questions (Google re:Work).",
                        "Research the employer's framework and tag your stories to it before the loop.",
                        "McKinsey's PEI goes deep on one story: Leadership, Connection, Drive, Growth.",
                    ],
                },
            ],
        },
        # ----------------------------------------------------------- B.6
        {
            "slug": "behavioral-special-questions",
            "title": "Special Questions & a Worked Example",
            "summary": (
                "'Tell me about yourself,' 'why this company,' 'greatest "
                "weakness,' the 5-year question, and salary — plus a strong vs "
                "weak STAR answer fully annotated."
            ),
            "source_refs": "Harvard FAS; The Muse; Robert Half",
            "est_minutes": 30,
            "lessons": [
                {
                    "slug": "tell-me-about-yourself",
                    "title": "'Tell me about yourself,' 'why us,' weakness, 5 years",
                    "source_refs": "Harvard FAS; The Muse; Indeed",
                    "body_md": (
                        "**Tell me about yourself.** Not a life story or a resume recital — a 60–90-second "
                        "**positioning pitch**. Use **Present → Past → Future**: who you are now and a "
                        "relevant achievement; the brief *relevant* path that got you here; why you're "
                        "excited about *this* role. End on the future so you hand the conversation toward "
                        "*\"why us.\"*\n\n"
                        "**Why do you want to work here / this role?** Show homework and two-way fit: "
                        "(1) something **specific and genuine** about the company (mission, a product, a "
                        "recent initiative — not *\"you're a leader in the space\"*); (2) how the role aligns "
                        "with your skills and goals; (3) what you'll contribute. Avoid reasons that are only "
                        "about you (salary, commute, prestige).\n\n"
                        "**Greatest weakness.** Be **honest but strategic**: name a *real* weakness that "
                        "isn't core to the job, ground it in a brief example, then spend most of the answer "
                        "on the **concrete steps you're taking** and the progress made. Skip the clichés "
                        "(*\"I'm a perfectionist\"*) — the signal is self-awareness + coachability.\n\n"
                        "**Where do you see yourself in 5 years?** Express a **realistic direction** "
                        "(growth in skills, scope, responsibility) plausibly reachable through this role, "
                        "and connect your growth to value for the company."
                    ),
                    "key_takeaways": [
                        "'Tell me about yourself' = Present → Past → Future, ~90 seconds.",
                        "'Why us' must be specific to the company, not generic flattery.",
                        "Weakness: real + not job-critical + concrete improvement plan.",
                    ],
                },
                {
                    "slug": "salary-questions",
                    "title": "Salary & compensation discussions",
                    "source_refs": "Robert Half; Coursera; Indeed",
                    "body_md": (
                        "Guidance converges across Robert Half, Indeed, and Coursera:\n\n"
                        "- **Timing / leverage.** Try not to raise pay first or too early; your leverage is "
                        "highest **after** they've decided they want you — ideally once you have a written "
                        "offer. Early *\"what are your expectations?\"* can be deflected: *\"I'd love to learn "
                        "more about the role first; I'm confident we can find a fair number.\"*\n"
                        "- **If pushed to name a figure**, give a **researched range** (market data for the "
                        "role/level/location) with your target near the bottom, anchored to your skills. By a "
                        "later round, be ready with an actual number.\n"
                        "- **Negotiate on the written offer**, consider **total compensation** (base, bonus, "
                        "equity, benefits, PTO, flexibility) — not just base — stay collaborative, and justify "
                        "your ask with evidence."
                    ),
                    "key_takeaways": [
                        "Delay specifics until they want you / you have an offer.",
                        "If forced, give a researched range anchored to market data.",
                        "Negotiate total comp on the written offer, professionally and with evidence.",
                    ],
                },
                {
                    "slug": "worked-example",
                    "title": "Worked example: a strong vs weak STAR answer",
                    "source_refs": "Synthesis of CtCI ch. 5 + MIT CAPD",
                    "body_md": (
                        "**Question:** *\"Tell me about a time you had to deal with a significant problem "
                        "under a tight deadline.\"*\n\n"
                        "**Strong answer (annotated):**\n\n"
                        "> *[Nugget]* \"This is the time I caught a data bug 36 hours before a major client "
                        "launch and shipped the fix without slipping the date.\n"
                        "> *[Situation ~20%]* I led reporting for our largest client's quarterly review. Two "
                        "days out, a final sanity check showed revenue ~12% too high.\n"
                        "> *[Task ~10%]* I owned the report's accuracy; the review was locked for 9 a.m. in two "
                        "days. Wrong numbers would cost credibility with a $4M client; slipping looked "
                        "disorganized.\n"
                        "> *[Action ~55%]* I reproduced the discrepancy and traced it to a join double-counting "
                        "refunds. Rather than hand-patch the report, I fixed the underlying query so it "
                        "couldn't recur, pulled in two teammates to validate the root cause while I rewrote the "
                        "transformation, and added a reconciliation check that flags any >1% variance against "
                        "finance. I re-ran and validated three quarters of history, and walked our account lead "
                        "through the corrected numbers the night before.\n"
                        "> *[Result ~10%]* We presented accurate numbers on time; the corrected figure changed "
                        "one recommendation, which the client adopted. The check has since caught two more "
                        "errors before they reached a client.\n"
                        "> *[Reflection]* I learned to fix the *system*, not the symptom — I now build a "
                        "validation step into every new report.\"\n\n"
                        "**Why it scores:** one concrete event; ~55% on the candidate's *actions*; relentlessly "
                        "*\"I\"*-forward; a **quantified** result with lasting impact; a genuine lesson; and it "
                        "demonstrates several competencies at once (ownership, bias for action, dive deep, "
                        "integrity).\n\n"
                        "**Weak version:** *\"We have tight deadlines all the time. There was this client "
                        "report, the numbers looked off, so the team dug in, we figured out it was some data "
                        "issue and fixed it before the meeting. It was stressful but we work well under "
                        "pressure. I think it shows I'm a hard worker.\"*\n\n"
                        "**Why it fails:** *\"we\"* throughout (your contribution is invisible); no specifics "
                        "(*\"some data issue\"*); no quantified result; the Action — where all the signal lives — "
                        "is two vague clauses; and it *tells* (*\"I'm a hard worker\"*) instead of *showing*."
                    ),
                    "key_takeaways": [
                        "Strong = nugget + one event + 'I'-led actions + a number + a lesson.",
                        "Weak = 'we', vague actions, no metric, and self-labels instead of evidence.",
                        "If you can't state the result as a number, pick a different story.",
                    ],
                },
            ],
        },
    ],
}
