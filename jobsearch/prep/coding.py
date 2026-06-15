"""Track 1: Coding Interview Foundations — distilled from
*Cracking the Coding Interview*, 6th Edition (Gayle Laakmann McDowell, 2015).

Each module corresponds to a chapter (or chapter cluster). Lesson bodies
quote the source's framing where the wording matters (Big-O rules,
five-step problem-solving framework, BUD optimization, etc.) and add
worked examples small enough to read in one sitting. Page numbers refer
to the 6e PDF in ``prep_work/``.
"""

TRACK_CODING = {
    "slug": "coding",
    "title": "Coding Interview Foundations",
    "description": (
        "Algorithms, data structures, and the problem-solving habits that turn "
        "a coding interview into a conversation. Distilled from "
        "Cracking the Coding Interview, 6e. Pair the lessons with the linked "
        "LeetCode problems to lock in each pattern."
    ),
    "modules": [
        # ---------------------------------------------------------- M1.1
        {
            "slug": "interview-process",
            "title": "The Interview Process & Behavioral Prep",
            "summary": (
                "How big-tech interviews are actually evaluated, what the "
                "process at each company looks like, and how to tell good "
                "stories about your work using S.A.R."
            ),
            "source_refs": "CtCI Pt. I–V, pp. 4–37",
            "est_minutes": 45,
            "lessons": [
                {
                    "slug": "why-algorithm-questions",
                    "title": "Why algorithm questions exist",
                    "source_refs": "CtCI pp. 16–19",
                    "body_md": (
                        "Companies use algorithm questions because they are a **noisy but cheap signal**\n"
                        "for problem-solving ability — the thing they actually care about. McDowell is\n"
                        "explicit (p. 16) that interviewers grade on five axes: analytical skills,\n"
                        "coding skills, technical knowledge, experience, and culture/communication.\n"
                        "Algorithm questions illuminate the first two at low cost.\n\n"
                        "Three implications follow from this:\n\n"
                        "1. **Performance is relative, not absolute (p. 19).** Your interviewer is\n"
                        "comparing you against everyone they've ever asked the same question. Struggling\n"
                        "is normal — what matters is your trajectory.\n\n"
                        "2. **False negatives are tolerated; false positives are not.** A great\n"
                        "candidate who has a bad day is acceptable collateral damage; a weak hire is\n"
                        "expensive. So the bar can feel arbitrary.\n\n"
                        "3. **Hints are not penalties.** Interviewers expect to give them, and good\n"
                        "candidates know how to accept and run with them (p. 18)."
                    ),
                    "key_takeaways": [
                        "Algorithm screens grade problem-solving, not memorized syntax.",
                        "You are graded relative to other candidates on the same question.",
                        "Asking for and using hints is part of the script — not a deduction.",
                    ],
                },
                {
                    "slug": "company-by-company",
                    "title": "What the big-tech loops actually look like",
                    "source_refs": "CtCI pp. 8–14",
                    "body_md": (
                        "McDowell walks through the published loops at six FAANG-era companies. The\n"
                        "useful summary:\n\n"
                        "- **Microsoft (p. 9)** — 4–5 interviews with one or two teams; you walk to\n"
                        "interviewers' offices. The recruiter screens first and is your advocate.\n"
                        "- **Amazon (p. 10)** — phone screen via shared document editor, then 4–5\n"
                        "on-sites in Seattle. A \"bar raiser\" sits in to enforce a high cross-team\n"
                        "standard; feedback is not discussed until the hiring meeting.\n"
                        "- **Google (p. 10)** — coding + design at scale; takes weeks to hear back.\n"
                        "- **Apple (p. 11)** — 4–5 interviews; specialized by product area.\n"
                        "- **Facebook (p. 12)** — coding-heavy; hackathon-culture references.\n"
                        "- **Palantir (p. 13)** — highly specialized; ownership and analysis.\n\n"
                        "The pattern across all of them: an on-site is a *day*, and you will be tired by\n"
                        "the fourth interview. Plan sleep, food, and travel as carefully as you plan\n"
                        "the technical prep."
                    ),
                    "key_takeaways": [
                        "Amazon has a bar raiser — a single high-bar interviewer from another team.",
                        "Microsoft and most others walk you between interviewer offices; budget for fatigue.",
                        "Recruiters at most companies (except Amazon style) are advocates, not adversaries.",
                    ],
                },
                {
                    "slug": "preparation-map",
                    "title": "The preparation map: 1 year → 1 week out",
                    "source_refs": "CtCI p. 30",
                    "body_md": (
                        "CtCI's Preparation Map (p. 30) gives a chronological breakdown most candidates\n"
                        "skim past:\n\n"
                        "- **1+ year out** — pick up languages, build projects, deepen the network.\n"
                        "- **3–6 months out** — read the front matter of this book; lock down Big O;\n"
                        "master the core data structures; ship a side project or two.\n"
                        "- **1–3 months out** — *mock interviews*. Track every mistake. Drill the\n"
                        "categories you flunk.\n"
                        "- **1–2 weeks out** — one last mock; rehearse your S.A.R. stories; review\n"
                        "Big-O for each data structure one more time.\n\n"
                        "The shape of this matters. If you have only two weeks, *do not* try to learn\n"
                        "DP from scratch; spend the time on mocks and on the categories you already\n"
                        "half-know."
                    ),
                    "key_takeaways": [
                        "Mocks belong in the last 1–3 months — don't substitute reading for them.",
                        "Track mistake patterns so the last week's review is targeted.",
                        "Two-week prep ≠ six-month prep — adjust scope, don't cram new topics.",
                    ],
                },
                {
                    "slug": "behavioral-sar",
                    "title": "Behavioral answers: nugget first, then S.A.R.",
                    "source_refs": "CtCI pp. 32–37",
                    "body_md": (
                        "McDowell prescribes two specific structures for behavioral answers (pp. 34–37):\n\n"
                        "- **Nugget First** — open with a one-sentence headline of the outcome, then\n"
                        "tell the story. Hooks the listener before the details lose them.\n"
                        "- **S.A.R. — Situation, Action, Result** — and *the Action is most of the\n"
                        "answer*. Most candidates compress the action and over-detail the situation;\n"
                        "the interviewer wants to know how *you* think.\n\n"
                        "Build a 5–7 column **Interview Preparation Grid** (p. 32). Rows are common\n"
                        "questions (\"hardest bug\", \"team conflict\", \"failure I learned from\");\n"
                        "columns are your projects. Each cell is a one-line story idea. Filling this\n"
                        "out before the loop is what lets you answer naturally rather than fishing for\n"
                        "a story under pressure.\n\n"
                        "Two reminders that catch even experienced candidates:\n"
                        "- Use **\"I,\" not \"we\"** — interviewers are scoring your individual\n"
                        "contribution.\n"
                        "- State facts, not adjectives — \"led a 4-person migration\" beats \"I'm great\n"
                        "at leadership.\""
                    ),
                    "key_takeaways": [
                        "Open with a one-sentence headline (\"Nugget First\") before the long version.",
                        "S.A.R. — and the Action carries the story, not the Situation.",
                        "Pre-fill an Interview Prep Grid mapping common questions to your projects.",
                    ],
                },
            ],
        },
        # ---------------------------------------------------------- M1.2
        {
            "slug": "big-o",
            "title": "Big O & Complexity Analysis",
            "summary": (
                "Time and space complexity is the language interviewers think in. Master "
                "the drop-constants rules, amortized analysis, and recursive runtime formulas."
            ),
            "source_refs": "CtCI Ch. VI, pp. 38–62",
            "est_minutes": 75,
            "lessons": [
                {
                    "slug": "time-and-space",
                    "title": "Time complexity vs. space complexity",
                    "source_refs": "CtCI pp. 38–40",
                    "body_md": (
                        "**Time complexity** asks how the runtime grows as input size n grows. The\n"
                        "shapes you will see in 95% of interviews are six: `O(1)`, `O(log n)`, `O(n)`,\n"
                        "`O(n log n)`, `O(n²)`, `O(2ⁿ)`. Recognizing which shape your solution lands\n"
                        "in is half the optimization conversation.\n\n"
                        "**Space complexity** is the memory required. *Stack frames count*: a recursive\n"
                        "`sum(n)` is O(n) time *and* O(n) space because n unfinished calls sit on the\n"
                        "stack. Tail-recursive or iterative rewrites can drop it to O(1).\n\n"
                        "Why this matters in interviews: when you say \"I can do this in O(n) time,\"\n"
                        "the next question is *\"and what's the space?\"* Mention both, every time."
                    ),
                    "key_takeaways": [
                        "Always state time *and* space — interviewers ask if you don't.",
                        "Recursion charges O(depth) for the call stack.",
                        "Memorize the six common shapes: 1, log n, n, n log n, n², 2ⁿ.",
                    ],
                },
                {
                    "slug": "drop-constants",
                    "title": "Drop the constants; drop the non-dominant terms",
                    "source_refs": "CtCI pp. 41–42",
                    "body_md": (
                        "Two rules from CtCI's Big-O chapter that show up on every whiteboard:\n\n"
                        "1. **Drop the constants** (p. 41). `O(2N)` is `O(N)`. Two for-loops in sequence\n"
                        "is one for-loop in Big-O — the constants 2× don't matter asymptotically.\n\n"
                        "2. **Drop non-dominant terms** (p. 42). `O(N² + N)` is `O(N²)`. Keep only the\n"
                        "fastest-growing term. `O(N + log N)` is `O(N)`.\n\n"
                        "Edge case: don't drop a term that's *not* dominated. `O(B² + A)` cannot be\n"
                        "simplified unless you know the relationship between A and B."
                    ),
                    "key_takeaways": [
                        "Constants vanish: O(2N) → O(N).",
                        "Non-dominant additive terms vanish: O(N² + N) → O(N²).",
                        "When variables are independent, both terms stay: O(A + B²).",
                    ],
                },
                {
                    "slug": "add-vs-multiply",
                    "title": "Multi-part algorithms: add vs. multiply",
                    "source_refs": "CtCI p. 42",
                    "body_md": (
                        "McDowell's mnemonic (p. 42):\n\n"
                        "- **\"Do this, then that\" → ADD.** Two sequential loops over A and B are\n"
                        "`O(A + B)`.\n"
                        "- **\"Do this FOR EACH of that\" → MULTIPLY.** A loop over A where each\n"
                        "iteration loops over B is `O(A × B)`.\n\n"
                        "Example: walking through array A and then walking through array B is `O(A + B)`.\n"
                        "Walking through A and for each element of A scanning B is `O(A × B)`.\n\n"
                        "Watch for the \"nested loop that breaks early\" trap — it's still O(A×B) worst\n"
                        "case unless you can prove the inner loop bound depends sub-linearly on A."
                    ),
                    "key_takeaways": [
                        "Sequential work → add. Nested work → multiply.",
                        "Two independent arrays: O(A + B), not O(A·B).",
                        "Early termination in a nested loop doesn't lower worst-case Big O.",
                    ],
                },
                {
                    "slug": "amortized-time",
                    "title": "Amortized time: ArrayList insertion",
                    "source_refs": "CtCI p. 43",
                    "body_md": (
                        "An `ArrayList` (Python `list`, Java `ArrayList`, C++ `vector`) appends in\n"
                        "**O(1) amortized** even though a single append can be O(n).\n\n"
                        "When the backing array fills, the implementation doubles its capacity and\n"
                        "copies all existing elements. Over n appends, the copies cost\n"
                        "`1 + 2 + 4 + 8 + … + n ≈ 2n`. Divide by n appends → ~2 copies *per append on\n"
                        "average*, i.e. O(1) amortized.\n\n"
                        "Interviewers love this because it tests whether you can reason about\n"
                        "*sequences of operations* rather than a single worst case. The same logic\n"
                        "powers hash table resizing (Chapter VI, p. 44)."
                    ),
                    "key_takeaways": [
                        "Doubling capacity = O(1) amortized append, despite O(n) worst-case copies.",
                        "Sum 1+2+4+…+n ≈ 2n is the trick that gets you there.",
                        "Hash tables resize the same way: O(1) amortized insert.",
                    ],
                },
                {
                    "slug": "log-n-runtimes",
                    "title": "Where O(log N) comes from",
                    "source_refs": "CtCI p. 44",
                    "body_md": (
                        "`O(log N)` shows up whenever the **problem space halves on each step**.\n"
                        "Canonical examples: binary search, traversal of a balanced BST, finding the\n"
                        "depth of a balanced tree.\n\n"
                        "The derivation (p. 44) is short: if it takes k steps to reduce the problem\n"
                        "to size 1, and each step halves the size, then `N / 2ᵏ = 1` → `k = log₂ N`.\n\n"
                        "Conversely: if the problem space halves, *assume* O(log N) is achievable —\n"
                        "even if the algorithm looks linear, look for the binary-search-shaped\n"
                        "optimization."
                    ),
                    "key_takeaways": [
                        "Halving the problem → log₂ N runtime.",
                        "Balanced BST height is log N — that's where insert/find gets its log.",
                        "If you see \"sorted\", \"monotonic\", or \"midpoint\" — try binary search.",
                    ],
                },
                {
                    "slug": "recursive-runtimes",
                    "title": "Recursive runtimes: branches^depth",
                    "source_refs": "CtCI pp. 44–45",
                    "body_md": (
                        "When a recursive function has **b** recursive calls per invocation and a\n"
                        "depth of **d**, runtime is `O(bᵈ)`.\n\n"
                        "Example (p. 44): `f(n) = f(n-1) + f(n-1)` has b=2, d=n, so `O(2ⁿ)`.\n"
                        "Fibonacci `f(n) = f(n-1) + f(n-2)` also has 2 branches but the depth is the\n"
                        "longer path: still about `O(2ⁿ)` without memoization. Add a memo and it drops\n"
                        "to O(n).\n\n"
                        "The recursion tree visualization makes this concrete: draw two children at\n"
                        "each node, the tree has 2ⁿ leaves at depth n. Don't be fooled by recursive\n"
                        "code that *looks* compact — count branches and depth."
                    ),
                    "key_takeaways": [
                        "Recursive runtime ≈ branches^depth.",
                        "Two branches and depth n → O(2ⁿ).",
                        "Memoization collapses the tree to O(n) by reusing subproblem answers.",
                    ],
                },
                {
                    "slug": "data-structure-cheatsheet",
                    "title": "Cheat sheet: data structure operations",
                    "source_refs": "CtCI Big-O chapter + Appendix",
                    "body_md": (
                        "Memorize the average-case operations on the structures that come up most:\n\n"
                        "| Structure | Access | Search | Insert | Delete |\n"
                        "|-----------|--------|--------|--------|--------|\n"
                        "| Array | O(1) | O(N) | O(N) | O(N) |\n"
                        "| Dynamic Array | O(1) | O(N) | O(1)* | O(N) |\n"
                        "| Hash Table | — | O(1) | O(1) | O(1) |\n"
                        "| Linked List | O(N) | O(N) | O(1) | O(1) |\n"
                        "| Stack / Queue | O(N) | O(N) | O(1) | O(1) |\n"
                        "| Balanced BST | O(log N) | O(log N) | O(log N) | O(log N) |\n"
                        "| Binary Heap | — | O(N) | O(log N) | O(log N) |\n"
                        "| Trie | — | O(M)† | O(M) | O(M) |\n\n"
                        "*amortized. †M = key length.\n\n"
                        "Sorts you should be able to recite (p. 146 cheatsheet):\n"
                        "- merge sort O(n log n) time, O(n) space, stable\n"
                        "- quicksort O(n log n) avg / O(n²) worst, O(log n) space, in-place\n"
                        "- radix sort O(kn), non-comparative"
                    ),
                    "key_takeaways": [
                        "Hash table: O(1) for search/insert/delete on average.",
                        "BST gives O(log N) only when balanced — note that explicitly.",
                        "Heap can find min/max in O(1) but search is O(N).",
                    ],
                },
            ],
        },
        # ---------------------------------------------------------- M1.3
        {
            "slug": "problem-solving-framework",
            "title": "The 5-Step Problem-Solving Framework",
            "summary": (
                "Listen → Example → Brute Force → Optimize → Walk Through → Code → Test. "
                "Plus the BUD optimization checklist."
            ),
            "source_refs": "CtCI Ch. VII, pp. 60–81",
            "est_minutes": 60,
            "lessons": [
                {
                    "slug": "listen-and-example",
                    "title": "Listen carefully, then build a real example",
                    "source_refs": "CtCI pp. 75–77",
                    "body_md": (
                        "Step 1 — **Listen** (p. 75). Every detail in the problem statement is a\n"
                        "hint at the optimal algorithm. \"Sorted array\" implies binary search. \"All\n"
                        "lowercase letters\" implies a 26-entry char count. \"Streaming\" rules out\n"
                        "anything that needs to see the whole input. Write the constraints down.\n\n"
                        "Step 2 — **Example** (p. 76). Most candidates draw a tiny, perfectly balanced\n"
                        "example: `[1, 2, 3, 4, 5]`. That's useless — it hides bugs. McDowell's\n"
                        "criteria for a good example:\n\n"
                        "- **Specific.** Use real numbers/strings, not `a, b, c`.\n"
                        "- **Sufficiently large.** Most candidates' first example is ~50% too small.\n"
                        "- **Not a special case.** Avoid sorted arrays, perfect trees, palindromes.\n"
                        "Make it unbalanced and asymmetric.\n\n"
                        "A good example is a debugging tool — bugs in your algorithm will show up in\n"
                        "the example before you write any code."
                    ),
                    "key_takeaways": [
                        "Treat every problem-statement word as a hint.",
                        "Example must be specific, large enough, and *not* a special case.",
                        "If your example would pass for the brute force and the optimum, it's too small.",
                    ],
                },
                {
                    "slug": "brute-force",
                    "title": "State the brute force immediately",
                    "source_refs": "CtCI p. 77",
                    "body_md": (
                        "Step 3 — **Brute Force**. McDowell is unambiguous: state a naive solution\n"
                        "*immediately*, even if it's obviously bad. Two reasons:\n\n"
                        "1. It proves you can solve the problem at all. The interviewer now knows you\n"
                        "won't leave with nothing.\n"
                        "2. It gives you a baseline to optimize. \"My brute force is O(n²). Let me see\n"
                        "where the redundancy is\" is the script that turns into the real solution.\n\n"
                        "Common candidate mistake: silently jumping to the optimum (or worse,\n"
                        "silently failing to find the optimum). Either way the interviewer doesn't\n"
                        "know what you can do. State the brute force out loud, even if it's so dumb\n"
                        "you wouldn't actually write it."
                    ),
                    "key_takeaways": [
                        "State a brute force before you optimize — out loud.",
                        "Always announce its time and space complexity.",
                        "The brute force is the baseline you'll improve from.",
                    ],
                },
                {
                    "slug": "bud-optimization",
                    "title": "BUD: Bottlenecks, Unnecessary work, Duplicated work",
                    "source_refs": "CtCI pp. 79–80",
                    "body_md": (
                        "Step 4 — **Optimize**. The single most useful checklist from CtCI is **BUD**\n"
                        "(pp. 79–80):\n\n"
                        "- **Bottlenecks.** If one part of the algorithm dominates (e.g., a sort that\n"
                        "is O(n log n) before an O(n) scan), the rest doesn't matter — optimize the\n"
                        "bottleneck or accept it.\n"
                        "- **Unnecessary work.** Are you computing things you don't need? Classic\n"
                        "example (p. 80): an equation solver iterating over a, b, c, *and* d, when d\n"
                        "is uniquely determined by a, b, c — drop the d loop.\n"
                        "- **Duplicated work.** Are you recomputing the same lookup? Cache it in a\n"
                        "hash table. The most common O(n²)→O(n) win in interviews.\n\n"
                        "Other tactics from the same section: look for unused information, solve\n"
                        "manually on a real example then reverse-engineer the pattern, and consider\n"
                        "a time-vs-space tradeoff via hash tables. State your **Best Conceivable\n"
                        "Runtime** (BCR, p. 72) — the theoretical lower bound — so you know when to\n"
                        "stop optimizing."
                    ),
                    "key_takeaways": [
                        "BUD = Bottlenecks, Unnecessary work, Duplicated work.",
                        "Duplicated work → hash table is the canonical fix.",
                        "BCR (Best Conceivable Runtime) tells you when to stop optimizing.",
                    ],
                },
                {
                    "slug": "walk-through-code-test",
                    "title": "Walk-through, code, test — in that order",
                    "source_refs": "CtCI pp. 77–78",
                    "body_md": (
                        "After optimizing, **walk through** the algorithm step-by-step before you\n"
                        "code (p. 77). Spell out variable states, edge cases, what changes per\n"
                        "iteration. This is the cheapest place to find bugs.\n\n"
                        "When coding (p. 77–78):\n"
                        "- **Modularize from the start.** Helper functions are easier to write than\n"
                        "to extract later.\n"
                        "- **Helper structs over loose vars.** A `StartEndPair` is clearer than two\n"
                        "parallel arrays.\n"
                        "- **Keep talking.** Silence is the killer — narrate as you write.\n\n"
                        "Testing (p. 78), in order:\n"
                        "1. **Conceptual** — read the code like a code review.\n"
                        "2. **Hot spots** — arithmetic, off-by-one, null pointers.\n"
                        "3. **Small test cases** — faster than the original example and just as\n"
                        "effective.\n"
                        "4. **Edge cases** — empty, single-element, all-equal, max/min.\n\n"
                        "When you find a bug, *understand why* before patching. \"Should this be `<`\n"
                        "or `<=`?\" is the wrong question; \"What invariant am I trying to keep?\" is\n"
                        "the right one."
                    ),
                    "key_takeaways": [
                        "Walk through before you code — it catches most bugs for free.",
                        "Helper structs > parallel arrays; modularize early.",
                        "Test order: conceptual → hot spots → small cases → edge cases.",
                    ],
                },
            ],
        },
        # ---------------------------------------------------------- M1.4
        {
            "slug": "arrays-and-strings",
            "title": "Arrays and Strings",
            "summary": (
                "Hash tables, dynamic arrays, StringBuilder, two-pointer techniques, "
                "in-place manipulation."
            ),
            "source_refs": "CtCI Ch. 1, pp. 88–104",
            "est_minutes": 60,
            "lessons": [
                {
                    "slug": "hash-tables",
                    "title": "Hash tables — the workhorse",
                    "source_refs": "CtCI p. 88",
                    "body_md": (
                        "A hash table maps keys to values via a hash function. **Average operations\n"
                        "are O(1)**; worst-case is O(n) when every key collides into the same bucket.\n\n"
                        "Collision resolution comes in two flavors:\n"
                        "- **Chaining** — each bucket holds a linked list of entries.\n"
                        "- **Open addressing** — probe to the next empty slot (linear probing,\n"
                        "quadratic probing, double hashing — pp. 636–637).\n\n"
                        "An alternative implementation uses a balanced BST: O(log n) operations and\n"
                        "less wasted space at the cost of speed.\n\n"
                        "Practically, in interviews: when you see \"find the X with property Y\" or\n"
                        "\"detect duplicates\", reach for a hash table first. It's how you turn most\n"
                        "O(n²) brute forces into O(n)."
                    ),
                    "key_takeaways": [
                        "Average O(1) for insert/search/delete; worst-case O(n).",
                        "Chaining (linked lists per bucket) vs. open addressing (probe sequence).",
                        "First instinct on \"detect duplicates\" or \"count occurrences\": hash table.",
                    ],
                },
                {
                    "slug": "dynamic-arrays",
                    "title": "Dynamic arrays and amortized append",
                    "source_refs": "CtCI p. 89",
                    "body_md": (
                        "A dynamic array (`ArrayList`, Python `list`, C++ `vector`) wraps a fixed\n"
                        "array and resizes when full. The growth pattern is to **double** capacity\n"
                        "when it fills, which gives **amortized O(1) insertion** (see the Big-O\n"
                        "module).\n\n"
                        "Read access stays O(1) by index. Insertion in the middle is O(n) because of\n"
                        "the shift. Search by value is O(n).\n\n"
                        "Why this matters: if you need an array but don't know its final size, a\n"
                        "dynamic array is free — the resizing cost averages out. If you do know the\n"
                        "size, pre-allocate. Both are interviewer-friendly answers."
                    ),
                    "key_takeaways": [
                        "Append is O(1) amortized via capacity doubling.",
                        "Indexed access is O(1); insertion in the middle is O(n).",
                        "Pre-allocate when you know the size; otherwise dynamic array is fine.",
                    ],
                },
                {
                    "slug": "stringbuilder",
                    "title": "StringBuilder and the O(xn²) string-concat trap",
                    "source_refs": "CtCI p. 89",
                    "body_md": (
                        "Concatenating n strings of average length x naively is **O(xn²)**, not O(xn).\n"
                        "Every concatenation copies the entire accumulated string into a new buffer:\n"
                        "x + 2x + 3x + … + nx ≈ x·n²/2.\n\n"
                        "A `StringBuilder` (or Python's `list.append` then `\"\".join`) avoids this by\n"
                        "appending into a resizable buffer and copying only when the buffer grows.\n"
                        "Final cost: **O(xn)**.\n\n"
                        "This is the kind of insight that turns into bonus interview points. When\n"
                        "you're building a string in a loop, call out the trap explicitly: \"Naive\n"
                        "concatenation here would be O(xn²); I'll use a StringBuilder for O(xn).\""
                    ),
                    "key_takeaways": [
                        "Naive string concatenation in a loop is O(xn²).",
                        "StringBuilder / list+join is O(xn).",
                        "Call out the optimization out loud — interviewers love this catch.",
                    ],
                },
                {
                    "slug": "two-pointers",
                    "title": "The two-pointer pattern",
                    "source_refs": "CtCI Ch. 1 problem set",
                    "body_md": (
                        "Many array/string problems collapse from O(n²) to O(n) with **two pointers**\n"
                        "that move toward each other or in the same direction at different speeds.\n\n"
                        "Three shapes worth memorizing:\n\n"
                        "1. **Opposite ends, moving inward** — Two Sum on a *sorted* array, palindrome\n"
                        "check, container-with-most-water. Decide based on the comparison which\n"
                        "pointer to move.\n"
                        "2. **Same direction, different speeds (sliding window)** — \"longest substring\n"
                        "without repeating\", \"smallest subarray with sum ≥ k\". Maintain an invariant\n"
                        "in the window, extend with one pointer, contract with the other.\n"
                        "3. **Slow/fast** — cycle detection in linked lists; finding the middle of a\n"
                        "list in one pass.\n\n"
                        "Recognition triggers: \"sorted array + pair-sum\", \"longest/smallest subarray\",\n"
                        "\"first repeating\", \"cycle\"."
                    ),
                    "key_takeaways": [
                        "Opposite-end pointers reduce sorted-array pair problems to O(n).",
                        "Sliding window handles \"longest/smallest contiguous\" problems in O(n).",
                        "Slow/fast pointers find list cycles and middles in O(n) with O(1) extra space.",
                    ],
                },
            ],
        },
        # ---------------------------------------------------------- M1.5
        {
            "slug": "linked-lists",
            "title": "Linked Lists",
            "summary": "Pointer hygiene, the runner technique, recursion on lists.",
            "source_refs": "CtCI Ch. 2, pp. 92–108",
            "est_minutes": 45,
            "lessons": [
                {
                    "slug": "linked-list-basics",
                    "title": "Singly vs. doubly linked — and why people pick one",
                    "source_refs": "CtCI pp. 92–93",
                    "body_md": (
                        "A **singly linked list** node carries a value and a `next` pointer. A\n"
                        "**doubly linked list** adds `prev`. The trade is one pointer per node\n"
                        "(memory) for O(1) backward traversal and easier deletion.\n\n"
                        "Operations:\n"
                        "- **Append at head**: O(1).\n"
                        "- **Append at tail**: O(1) *if* you keep a tail pointer, otherwise O(n).\n"
                        "- **Search**: O(n) — no random access.\n"
                        "- **Delete given the node**: O(1) for doubly linked; O(1) for singly if you\n"
                        "have the *previous* node, O(n) if you don't.\n\n"
                        "Practical note (p. 93): in interviews, deletion in a singly linked list is\n"
                        "almost always presented as \"delete this node given a pointer to it\". The\n"
                        "trick: copy the next node's value into this node, then delete the next\n"
                        "node — a one-line stunt that catches candidates who go looking for the\n"
                        "predecessor."
                    ),
                    "key_takeaways": [
                        "Doubly linked = O(1) bidirectional traversal at the cost of one extra pointer.",
                        "Tail pointer is free for O(1) appends — keep one when you need them.",
                        "Singly-linked delete with no predecessor: copy next.value, delete next.",
                    ],
                },
                {
                    "slug": "runner-technique",
                    "title": "The runner technique (slow + fast pointers)",
                    "source_refs": "CtCI p. 93",
                    "body_md": (
                        "Two pointers traverse the list at different speeds. This unlocks three\n"
                        "canonical patterns:\n\n"
                        "1. **Find the middle** in one pass — slow advances 1, fast advances 2; when\n"
                        "fast hits the end, slow is at the middle.\n"
                        "2. **Detect a cycle (Floyd's algorithm)** — same speeds; if they meet, there's\n"
                        "a cycle. To find the *start* of the cycle, reset one pointer to head and\n"
                        "advance both by 1 — they meet at the cycle entry.\n"
                        "3. **Find nth-to-last** — advance fast by n first, then advance both together\n"
                        "until fast hits the end. Slow is at the nth-to-last.\n\n"
                        "All three avoid the temptation to first compute the length and then\n"
                        "traverse a second time. They're O(n) time, O(1) extra space — the cleanest\n"
                        "answer in an interview."
                    ),
                    "key_takeaways": [
                        "Two pointers at different speeds find middles, cycles, and nth-from-end in one pass.",
                        "Floyd's cycle detection: meet inside the loop, then reset one pointer to head.",
                        "All variants are O(n) time, O(1) space.",
                    ],
                },
                {
                    "slug": "recursion-on-lists",
                    "title": "Recursion on linked lists",
                    "source_refs": "CtCI p. 93",
                    "body_md": (
                        "Linked lists are recursion-friendly: each node is the head of a smaller\n"
                        "list. Patterns:\n\n"
                        "- **Reverse a list recursively**: reverse the tail, then point\n"
                        "`head.next.next = head` and null out `head.next`. Base case is empty or\n"
                        "single-node list.\n"
                        "- **Palindrome check**: walk to the end recursively while comparing with a\n"
                        "front pointer carried in shared state (or a wrapper class).\n"
                        "- **Sum of two lists as numbers**: recurse, carry as the second return value.\n\n"
                        "All of these are O(n) time and O(n) space — recursion adds a stack frame\n"
                        "per node. If interviewers ask for O(1) space, convert to iterative; the\n"
                        "code is harder but the conversion is mechanical (use an explicit stack or\n"
                        "track previous-node manually)."
                    ),
                    "key_takeaways": [
                        "Each node = head of a smaller list — natural recursion.",
                        "Recursive list code is O(n) extra space (stack frames).",
                        "Iterative reversal is the canonical O(1)-space pattern — memorize it.",
                    ],
                },
            ],
        },
        # ---------------------------------------------------------- M1.6
        {
            "slug": "stacks-and-queues",
            "title": "Stacks and Queues",
            "summary": "LIFO and FIFO; the canonical applications (DFS, BFS, parsing).",
            "source_refs": "CtCI Ch. 3, pp. 96–113",
            "est_minutes": 35,
            "lessons": [
                {
                    "slug": "stack-operations",
                    "title": "Stack: LIFO; push/pop/peek in O(1)",
                    "source_refs": "CtCI p. 96",
                    "body_md": (
                        "A stack stores elements last-in-first-out: think of a stack of plates.\n"
                        "Operations: `push`, `pop`, `peek`, `is_empty` — all O(1).\n\n"
                        "Implement with either an array (use the array length as the top pointer) or\n"
                        "a singly linked list (head is the top).\n\n"
                        "Three places stacks always come up in interviews:\n"
                        "- **DFS** on trees and graphs — recursion *is* a stack; you can also\n"
                        "implement it explicitly.\n"
                        "- **Balanced-parentheses / expression evaluation** — push opens, pop and\n"
                        "match on closes.\n"
                        "- **Undo / back button** — a stack of past states.\n\n"
                        "A classic CtCI sub-problem: implement a `Min Stack` where `getMin()` is O(1).\n"
                        "Hold a parallel stack of running minimums."
                    ),
                    "key_takeaways": [
                        "All ops O(1); implement with array or linked list.",
                        "Stacks back DFS, parsing/matching, and undo histories.",
                        "Min Stack pattern: parallel stack of running minimums.",
                    ],
                },
                {
                    "slug": "queue-operations",
                    "title": "Queue: FIFO; enqueue/dequeue in O(1)",
                    "source_refs": "CtCI p. 97",
                    "body_md": (
                        "A queue stores elements first-in-first-out. Operations: `enqueue` (back),\n"
                        "`dequeue` (front), `peek`, `is_empty` — all O(1).\n\n"
                        "Implement with a doubly linked list (head + tail pointers) or a circular\n"
                        "array. A singly linked list with both head and tail pointers also works.\n\n"
                        "Canonical applications:\n"
                        "- **BFS** on trees and graphs — level-order traversal.\n"
                        "- **Task queues** in producer/consumer setups.\n"
                        "- **Level-aware traversal** when you need to know which level you're on.\n\n"
                        "Worth memorizing: a queue from two stacks (CtCI 3.4). Push onto stack A;\n"
                        "when you need to pop the queue, dump A into B and pop from B. Amortized\n"
                        "O(1)."
                    ),
                    "key_takeaways": [
                        "FIFO; all ops O(1) with head + tail pointers.",
                        "Queues drive BFS and producer/consumer task processing.",
                        "Queue-from-two-stacks pattern: amortized O(1).",
                    ],
                },
            ],
        },
        # ---------------------------------------------------------- M1.7
        {
            "slug": "trees-and-graphs",
            "title": "Trees and Graphs",
            "summary": (
                "Tree types, traversals, BFS vs. DFS, tries, heaps, and shortest-path basics."
            ),
            "source_refs": "CtCI Ch. 4, pp. 100–125",
            "est_minutes": 90,
            "lessons": [
                {
                    "slug": "tree-types",
                    "title": "Tree taxonomy: balanced, complete, full, perfect",
                    "source_refs": "CtCI p. 100",
                    "body_md": (
                        "Interviewers will use these terms loosely; you should be precise:\n\n"
                        "- **Balanced** — not terribly imbalanced; informally, all operations stay\n"
                        "O(log n). Red-black and AVL trees (pp. 637–639) are balanced.\n"
                        "- **Complete** — every level fully filled *except* possibly the last, which\n"
                        "is filled left-to-right.\n"
                        "- **Full** — every node has 0 or 2 children. No singletons.\n"
                        "- **Perfect** — both full *and* complete. All leaves at the same depth.\n"
                        "Rare; only exists when nodes = 2ᵏ − 1.\n\n"
                        "Binary Search Tree (BST) adds an *ordering* invariant: for each node, all\n"
                        "left descendants are ≤ node ≤ all right descendants. Unbalanced BSTs\n"
                        "degenerate to O(n) operations — which is why balanced BSTs exist."
                    ),
                    "key_takeaways": [
                        "Balanced = the operations stay logarithmic.",
                        "Complete = fill left-to-right; Full = 0 or 2 children; Perfect = both.",
                        "BST adds an ordering invariant; unbalanced BSTs degenerate to O(n).",
                    ],
                },
                {
                    "slug": "tree-traversals",
                    "title": "In-order, pre-order, post-order",
                    "source_refs": "CtCI p. 103",
                    "body_md": (
                        "All three traversals visit every node — they only differ in *when* they\n"
                        "visit the current node relative to its children. All are O(n) time and\n"
                        "O(h) space (h = tree height).\n\n"
                        "- **In-order** — Left → Node → Right. On a BST this yields **ascending**\n"
                        "order. The most common interview traversal.\n"
                        "- **Pre-order** — Node → Left → Right. Useful for *copying* a tree.\n"
                        "- **Post-order** — Left → Right → Node. Useful for *deleting* a tree\n"
                        "(children freed before parents) and for computing things that depend on\n"
                        "subtree results (heights, sums).\n\n"
                        "**BFS / level-order** is the fourth traversal you'll need — it uses a\n"
                        "queue, not recursion, and visits nodes level-by-level."
                    ),
                    "key_takeaways": [
                        "In-order on a BST = sorted order.",
                        "Pre-order copies a tree; post-order destroys one or computes from leaves up.",
                        "BFS / level-order uses a queue; the other three use a stack (or recursion).",
                    ],
                },
                {
                    "slug": "heaps",
                    "title": "Binary heaps and priority queues",
                    "source_refs": "CtCI p. 103",
                    "body_md": (
                        "A **min-heap** is a complete binary tree where each parent ≤ its children.\n"
                        "(Max-heap reverses the inequality.) Implemented as an array: for index i,\n"
                        "children are at 2i+1 and 2i+2.\n\n"
                        "Operations:\n"
                        "- **`insert`**: O(log n). Add at the next slot, bubble up.\n"
                        "- **`extract_min`**: O(log n). Swap root with last, remove last, bubble\n"
                        "down.\n"
                        "- **`peek_min`**: O(1).\n\n"
                        "Heaps power **priority queues**, **Dijkstra's algorithm**, and the **top-k**\n"
                        "pattern. The top-k trick: keep a min-heap of size k; for each incoming\n"
                        "element, if it's larger than the heap min, pop the min and push the new\n"
                        "element. Final heap holds the k largest. O(n log k) — better than O(n log n)\n"
                        "for large n, small k."
                    ),
                    "key_takeaways": [
                        "Min-heap: parent ≤ children; insert and extract are O(log n).",
                        "Array-backed: children of i are at 2i+1, 2i+2.",
                        "Top-k pattern: min-heap of size k → O(n log k).",
                    ],
                },
                {
                    "slug": "tries",
                    "title": "Tries (prefix trees)",
                    "source_refs": "CtCI p. 105",
                    "body_md": (
                        "A **trie** stores a set of strings as a tree of characters. Each path from\n"
                        "the root to a marked node is a stored string. Lookups, inserts, and prefix\n"
                        "queries are O(m), where m is the length of the key — *independent of the\n"
                        "number of stored strings*.\n\n"
                        "Where tries beat hash tables:\n"
                        "- **Autocomplete** — find all strings sharing a prefix in O(m + matches).\n"
                        "- **Spell-check** — bounded-edit-distance traversal of the trie.\n"
                        "- **Longest-common-prefix** queries.\n\n"
                        "Space cost: one node per character per unique prefix. Compact alternatives\n"
                        "(radix trees, DAFSAs) trade implementation complexity for memory.\n\n"
                        "Comes back as a building block in **System Design Interview Ch. 13**\n"
                        "(Search Autocomplete) — see the System Design track."
                    ),
                    "key_takeaways": [
                        "Search/insert in O(key length), independent of how many strings are stored.",
                        "Best fit for prefix and autocomplete problems.",
                        "Space cost grows with unique prefixes; use radix trees for compression.",
                    ],
                },
                {
                    "slug": "graphs-representation",
                    "title": "Graph representation: adjacency list vs. matrix",
                    "source_refs": "CtCI p. 105",
                    "body_md": (
                        "Two common representations:\n\n"
                        "- **Adjacency list** — for each node, a list of its neighbors. Space O(V+E).\n"
                        "Best for sparse graphs (most real-world graphs).\n"
                        "- **Adjacency matrix** — V×V boolean matrix. Space O(V²). Best for dense\n"
                        "graphs and for constant-time edge lookup.\n\n"
                        "Most interview graphs are sparse — default to adjacency list.\n\n"
                        "Other terminology you should be fluent in:\n"
                        "- **Directed vs. undirected**.\n"
                        "- **Weighted vs. unweighted**.\n"
                        "- **Connected vs. disconnected** — a graph may have multiple components.\n"
                        "- **DAG** — directed acyclic graph; what topological sort needs."
                    ),
                    "key_takeaways": [
                        "Adjacency list O(V+E) for sparse; matrix O(V²) for dense.",
                        "Default to adjacency list unless you need O(1) edge lookup.",
                        "Know the words: directed, weighted, connected, DAG.",
                    ],
                },
                {
                    "slug": "bfs-dfs",
                    "title": "BFS vs. DFS: when to use which",
                    "source_refs": "CtCI p. 107",
                    "body_md": (
                        "Both visit every reachable node in O(V + E). They differ in *order* — and\n"
                        "that's the entire choice.\n\n"
                        "- **BFS** (queue): level-by-level, nearest-first. Use when the answer is\n"
                        "**\"shortest path in an unweighted graph\"** or **\"closest match\"** or\n"
                        "**\"level\"**. Marks visited *as it enqueues* (not as it dequeues), or you'll\n"
                        "double-enqueue.\n"
                        "- **DFS** (recursion or stack): depth-first, backtracking. Use for\n"
                        "**connectivity**, **cycle detection**, **topological sort**, and\n"
                        "**path-existence** when the path's length doesn't matter.\n\n"
                        "**Bidirectional search** (p. 107) — search forward from source *and*\n"
                        "backward from target. Halves the depth, reducing complexity from O(bᵈ) to\n"
                        "O(b^(d/2)).\n\n"
                        "For weighted graphs with non-negative weights, use **Dijkstra's**\n"
                        "(p. 633) — BFS with a priority queue."
                    ),
                    "key_takeaways": [
                        "BFS for shortest path in unweighted graphs; DFS for connectivity/cycles.",
                        "Mark visited on enqueue, not dequeue, for BFS — else you'll double-process.",
                        "Bidirectional search halves the depth: O(bᵈ) → O(b^(d/2)).",
                    ],
                },
            ],
        },
        # ---------------------------------------------------------- M1.8
        {
            "slug": "recursion-and-dp",
            "title": "Recursion and Dynamic Programming",
            "summary": (
                "Recursive thinking, memoization, tabulation, classic DP patterns "
                "(Fibonacci, knapsack, climbing stairs)."
            ),
            "source_refs": "CtCI Ch. 8, pp. 130–148",
            "est_minutes": 90,
            "lessons": [
                {
                    "slug": "recursive-mindset",
                    "title": "The recursive mindset",
                    "source_refs": "CtCI pp. 130–131",
                    "body_md": (
                        "Recursion shines when a problem can be solved by solving smaller versions\n"
                        "of *itself*. The mantra: **express the answer for size n in terms of\n"
                        "answer(s) for sizes < n.**\n\n"
                        "Three common shapes:\n"
                        "- **Bottom-up** — solve for size 1, then 2, then 3, …\n"
                        "- **Top-down** — assume f(n-1) is solved; combine with current to make f(n).\n"
                        "- **Half-and-half** — split into two halves of size n/2 (binary search,\n"
                        "merge sort).\n\n"
                        "Every recursive solution can be made iterative, but the conversion costs\n"
                        "you readability and gets you O(1) call-stack space. The right answer in\n"
                        "interviews is usually: recursive first for clarity, then mention the\n"
                        "iterative version exists if asked."
                    ),
                    "key_takeaways": [
                        "Recursion = answer(n) in terms of answer(< n).",
                        "Bottom-up vs. top-down vs. half-and-half — all are recursion.",
                        "Recursive code: O(depth) call-stack space — call it out.",
                    ],
                },
                {
                    "slug": "memoization-tabulation",
                    "title": "Memoization vs. tabulation",
                    "source_refs": "CtCI pp. 131–135",
                    "body_md": (
                        "Dynamic programming = **recursion with memoization** (top-down) or\n"
                        "**iteration over a table** (bottom-up). Same answers, same complexities —\n"
                        "different code shape.\n\n"
                        "Canonical example: Fibonacci.\n"
                        "- Naive recursive: `f(n) = f(n-1) + f(n-2)` — **O(2ⁿ)** because the\n"
                        "subproblems get recomputed.\n"
                        "- **Memoized**: cache f(0), f(1), … f(n) in a hash or array. **O(n)** time,\n"
                        "O(n) space.\n"
                        "- **Tabulation**: iterative loop filling `dp[0..n]`. **O(n)** time, O(n)\n"
                        "space (or O(1) if you only need the last two values).\n\n"
                        "Recognize DP candidates by: overlapping subproblems + optimal substructure.\n"
                        "If your recursive solution branches and visits the same subproblems —\n"
                        "memoize."
                    ),
                    "key_takeaways": [
                        "DP = recursion + memo, or iterative tabulation. Same answer, different shape.",
                        "Memoize the moment you see overlapping subproblems.",
                        "Naive Fibonacci is O(2ⁿ); memoized or tabulated is O(n).",
                    ],
                },
                {
                    "slug": "classic-dp-patterns",
                    "title": "Classic DP patterns to know cold",
                    "source_refs": "CtCI problem set 8.x",
                    "body_md": (
                        "Six shapes cover the majority of interview DP:\n\n"
                        "1. **Climbing stairs / Fibonacci variants** — `dp[i] = dp[i-1] + dp[i-2]`.\n"
                        "2. **House robber** — `dp[i] = max(dp[i-1], dp[i-2] + nums[i])`.\n"
                        "3. **Coin change** (min coins) — `dp[amount] = min(dp[amount - coin] + 1)`\n"
                        "for each coin.\n"
                        "4. **Longest Increasing Subsequence** — O(n²) DP or O(n log n) with patience.\n"
                        "5. **Edit distance / LCS** — 2D DP on two strings.\n"
                        "6. **0/1 knapsack** — 2D DP indexed by (item, capacity).\n\n"
                        "Memorize the recurrences. In an interview, you don't have time to *derive*\n"
                        "them from scratch — you need to recognize the shape and adapt. Practice on\n"
                        "LeetCode and you'll start seeing the pattern by problem-statement keywords."
                    ),
                    "key_takeaways": [
                        "Six DP shapes cover most interviews — memorize the recurrences.",
                        "1D DP (Fib, robber, coin) is the most common; 2D shows up for strings/knapsack.",
                        "Keyword triggers: \"max/min/count of ways\" + \"step/choice\".",
                    ],
                },
            ],
        },
        # ---------------------------------------------------------- M1.9
        {
            "slug": "sorting-and-searching",
            "title": "Sorting and Searching",
            "summary": "When to reach for each sort; binary search in its many guises.",
            "source_refs": "CtCI Ch. 10, pp. 146–164",
            "est_minutes": 45,
            "lessons": [
                {
                    "slug": "sort-choice",
                    "title": "Picking the right sort",
                    "source_refs": "CtCI pp. 146–148",
                    "body_md": (
                        "From CtCI's cheatsheet (p. 146):\n\n"
                        "| Algorithm | Avg | Worst | Space | Stable | Notes |\n"
                        "|-----------|-----|-------|-------|--------|-------|\n"
                        "| Merge sort | O(n log n) | O(n log n) | O(n) | Yes | Predictable, parallel-friendly |\n"
                        "| Quicksort | O(n log n) | O(n²) | O(log n) | No | Fastest in practice; pivot matters |\n"
                        "| Heapsort | O(n log n) | O(n log n) | O(1) | No | In-place but slower than quicksort in practice |\n"
                        "| Insertion sort | O(n²) | O(n²) | O(1) | Yes | Great for small or nearly-sorted inputs |\n"
                        "| Radix sort | O(kn) | O(kn) | O(n) | Yes | Non-comparative; integers/strings only |\n\n"
                        "Default to **quicksort** in interviews unless something specific changes\n"
                        "the answer:\n"
                        "- **Stable sort needed?** → merge sort.\n"
                        "- **Strict O(n log n) worst-case needed?** → merge sort or heapsort.\n"
                        "- **Integer keys with bounded range?** → counting / radix.\n"
                        "- **Nearly sorted input?** → insertion sort (O(n) best case)."
                    ),
                    "key_takeaways": [
                        "Default: quicksort. Worst-case-bounded: merge sort or heapsort.",
                        "Stable sort needed → merge sort.",
                        "Radix/counting sort breaks the O(n log n) bound for bounded integer keys.",
                    ],
                },
                {
                    "slug": "binary-search-variants",
                    "title": "Binary search and its many variants",
                    "source_refs": "CtCI p. 149",
                    "body_md": (
                        "Vanilla binary search: O(log n) on a sorted array. Where it gets\n"
                        "interesting is the variants interviewers ask:\n\n"
                        "- **Find first / last occurrence** of a value — adjust the boundary handling\n"
                        "to keep searching after a match.\n"
                        "- **Search in a rotated sorted array** (CtCI 10.3) — at each midpoint, decide\n"
                        "which half is sorted, then check whether the target is in it.\n"
                        "- **Search a sorted array with unknown length** (CtCI 10.4) — double an index\n"
                        "until you overshoot, then binary search the bracket.\n"
                        "- **Binary search on the answer** — when the search space is a *value range*\n"
                        "(e.g., \"smallest capacity that finishes in K days\"). The check function\n"
                        "becomes the predicate.\n\n"
                        "Memorize the `[lo, hi]` vs. `[lo, hi)` invariant you use. The number of\n"
                        "off-by-one bugs in binary search is legendary; pick one style and stick to\n"
                        "it."
                    ),
                    "key_takeaways": [
                        "Binary search is O(log n) — but only on a monotonic search space.",
                        "\"Binary search on the answer\" works when the predicate is monotonic.",
                        "Pick one bracket convention ([lo, hi] or [lo, hi)) and never mix.",
                    ],
                },
            ],
        },
        # ---------------------------------------------------------- M1.10
        {
            "slug": "object-oriented-design",
            "title": "Object-Oriented Design",
            "summary": (
                "The 4-step approach to OOD problems, common design patterns (Singleton, "
                "Factory), and how to talk about classes in an interview."
            ),
            "source_refs": "CtCI Ch. 7, pp. 125–142",
            "est_minutes": 40,
            "lessons": [
                {
                    "slug": "ood-four-steps",
                    "title": "The 4-step OOD approach",
                    "source_refs": "CtCI pp. 125–126",
                    "body_md": (
                        "CtCI prescribes (pp. 125–126):\n\n"
                        "1. **Handle ambiguity** — who uses this? what are the constraints? — *ask*.\n"
                        "OOD prompts are intentionally vague.\n"
                        "2. **Define the core objects** — the major entities. \"Design a parking lot\"\n"
                        "→ `ParkingLot`, `Level`, `Spot`, `Vehicle`. The list is a conversation\n"
                        "with the interviewer, not a one-shot.\n"
                        "3. **Analyze relationships** — one-to-many, many-to-many, inheritance.\n"
                        "*Don't over-generalize* (a `Vehicle` superclass is fine; a `Movable`\n"
                        "abstract is too far).\n"
                        "4. **Investigate actions** — what do the objects *do*? What's the flow when\n"
                        "a vehicle enters? This step often reveals a missing class.\n\n"
                        "Keep it concrete — interviewers want a system you could implement this\n"
                        "afternoon, not a Java spec."
                    ),
                    "key_takeaways": [
                        "Always ask clarifying questions — OOD prompts are deliberately vague.",
                        "Define core objects → relationships → actions, in that order.",
                        "Don't over-generalize. \"Parking lot\" needs a Spot, not a Movable abstract.",
                    ],
                },
                {
                    "slug": "design-patterns",
                    "title": "Singleton and Factory patterns",
                    "source_refs": "CtCI p. 126",
                    "body_md": (
                        "Two patterns come up enough to be worth knowing by name:\n\n"
                        "**Singleton** — exactly one instance, global access through `getInstance()`.\n"
                        "Use for shared resources (logger, DB connection pool). Drawbacks: hard to\n"
                        "test (global state), thread-safety is non-trivial. In interviews, *call out*\n"
                        "the drawbacks if you use it.\n\n"
                        "**Factory Method** — an interface for creating instances; subclasses decide\n"
                        "the concrete class. Useful when client code shouldn't know which subclass\n"
                        "is being created. The classic example: a `ShapeFactory` that returns the\n"
                        "right `Shape` subtype based on a string parameter.\n\n"
                        "Beyond these two, the standard \"Gang of Four\" patterns (Observer, Strategy,\n"
                        "Decorator) are nice-to-know but rarely directly tested. The deeper signal\n"
                        "interviewers want is *single responsibility* and *separation of concerns*."
                    ),
                    "key_takeaways": [
                        "Singleton: one instance, global access — call out test/thread-safety costs.",
                        "Factory: client doesn't know the concrete class.",
                        "Above patterns: \"single responsibility\" and \"separation of concerns\" matter most.",
                    ],
                },
            ],
        },
        # ---------------------------------------------------------- M1.11
        {
            "slug": "bit-manipulation",
            "title": "Bit Manipulation",
            "summary": "AND/OR/XOR/NOT, two's complement, the six core bit operations.",
            "source_refs": "CtCI Ch. 5, pp. 112–129",
            "est_minutes": 30,
            "lessons": [
                {
                    "slug": "bit-basics",
                    "title": "Bitwise ops and two's complement",
                    "source_refs": "CtCI pp. 112–113",
                    "body_md": (
                        "The four bitwise ops:\n"
                        "- `a & b` — AND. Bit is 1 only if both bits are 1.\n"
                        "- `a | b` — OR. Bit is 1 if either is 1.\n"
                        "- `a ^ b` — XOR. Bit is 1 if exactly one is 1.\n"
                        "- `~a` — NOT. Flip every bit.\n\n"
                        "Shifts:\n"
                        "- `a << k` — left shift; multiplies by 2ᵏ.\n"
                        "- `a >> k` — right shift. **Arithmetic** right shift preserves the sign bit\n"
                        "(divide-by-2 for signed). **Logical** right shift (`>>>` in Java) fills with\n"
                        "0 (treat as unsigned).\n\n"
                        "**Two's complement** (p. 113): negative numbers are stored as `~x + 1`.\n"
                        "`-1` is all 1 bits. This is why `x & -x` isolates the lowest set bit — a\n"
                        "trick worth remembering."
                    ),
                    "key_takeaways": [
                        "XOR (^) is the workhorse — it's how you toggle, swap, and detect uniques.",
                        "Arithmetic right shift preserves sign; logical right shift fills with 0.",
                        "`x & -x` isolates the lowest set bit — two's complement trick.",
                    ],
                },
                {
                    "slug": "common-bit-tasks",
                    "title": "Get / set / clear / update bit",
                    "source_refs": "CtCI p. 114",
                    "body_md": (
                        "The six idioms McDowell prescribes (p. 114):\n\n"
                        "- **Get bit i:** `(num & (1 << i)) != 0`\n"
                        "- **Set bit i:** `num | (1 << i)`\n"
                        "- **Clear bit i:** `num & ~(1 << i)`\n"
                        "- **Update bit i to v:** `(num & ~(1 << i)) | (v << i)`\n"
                        "- **Clear MSB through bit i:** `num & ((1 << i) - 1)`\n"
                        "- **Clear bit i through 0:** `num & (~0 << (i + 1))`\n\n"
                        "Two follow-on tricks worth remembering:\n"
                        "- **Count set bits**: `n & (n-1)` clears the lowest set bit. Loop until n=0;\n"
                        "the iteration count is the popcount. O(set bits) instead of O(width).\n"
                        "- **Check power of two**: `n > 0 && (n & (n-1)) == 0`."
                    ),
                    "key_takeaways": [
                        "Memorize the six idioms — get/set/clear/update/clear-MSB/clear-LSB.",
                        "`n & (n-1)` clears the lowest set bit — used for popcount and power-of-2 check.",
                        "Bit tricks live in compiler optimizations, hash table sizing, and bloom filters.",
                    ],
                },
            ],
        },
        # ---------------------------------------------------------- M1.12
        {
            "slug": "ctci-system-design-intro",
            "title": "System Design (CtCI primer)",
            "summary": (
                "CtCI's compact 5-step system-design framework — a warmup for the dedicated "
                "System Design track."
            ),
            "source_refs": "CtCI Ch. 9, pp. 137–158",
            "est_minutes": 30,
            "lessons": [
                {
                    "slug": "ctci-sd-five-steps",
                    "title": "CtCI's 5-step system design",
                    "source_refs": "CtCI pp. 138–143",
                    "body_md": (
                        "McDowell's compact framework (pp. 138–143) for the design portion of a\n"
                        "coding interview:\n\n"
                        "1. **Scope the problem** — what features? what's out of scope?\n"
                        "2. **Make reasonable assumptions** — \"1M URLs/day, 100M users\" — state\n"
                        "them aloud.\n"
                        "3. **Draw major components** — frontend, backend, datastore, analytics —\n"
                        "as boxes on the board.\n"
                        "4. **Identify key issues** — bottlenecks, single points of failure, data\n"
                        "consistency.\n"
                        "5. **Redesign for the key issues** — caching, sharding, replication, async\n"
                        "queues. Discuss what you give up at each step.\n\n"
                        "This is the same framework as Xu's, just compressed. **For deeper coverage\n"
                        "of each technique** — load balancers, caching, sharding, consistent hashing,\n"
                        "and 15 worked design problems — go to the **System Design track** next."
                    ),
                    "key_takeaways": [
                        "5 steps: scope → assume → draw → identify issues → redesign.",
                        "Always state assumptions out loud — they're hypotheses, not commitments.",
                        "No \"perfect\" system: every fix gives up something (consistency, cost, latency).",
                    ],
                },
            ],
        },
        # ---------------------------------------------------------- M1.13
        {
            "slug": "testing",
            "title": "Testing",
            "summary": "What to test, in what order, and how to design tests for messy systems.",
            "source_refs": "CtCI Ch. 11, pp. 152–168",
            "est_minutes": 30,
            "lessons": [
                {
                    "slug": "what-interviewer-wants",
                    "title": "What testing interviewers actually grade",
                    "source_refs": "CtCI p. 152",
                    "body_md": (
                        "Three signals (p. 152):\n\n"
                        "- **Coverage** — did you find the boundary cases, the nulls, the unusual\n"
                        "inputs?\n"
                        "- **Logical thinking** — can you explain *why* each test matters?\n"
                        "- **Communication** — can you classify and prioritize? \"Here are five\n"
                        "categories of tests; let me start with the most critical.\"\n\n"
                        "The framing matters: testing questions aren't about exhaustive lists, they\n"
                        "are about *structured thinking*. Group your tests, justify the groups, then\n"
                        "drill down."
                    ),
                    "key_takeaways": [
                        "Interviewers grade structure, not exhaustive lists.",
                        "Group tests by category and justify each.",
                        "Communication > coverage — explain why each test catches something.",
                    ],
                },
                {
                    "slug": "edge-cases-checklist",
                    "title": "Edge cases checklist",
                    "source_refs": "CtCI pp. 153–155",
                    "body_md": (
                        "When asked to \"test a function\" or \"test a feature\", walk this checklist:\n\n"
                        "- **Empty / null** — empty string, empty array, null pointer.\n"
                        "- **Single-element** — one item, one user, one byte.\n"
                        "- **Extremes** — `INT_MAX`, `INT_MIN`, max-length string, all-same-value.\n"
                        "- **Negative / zero** — for numeric inputs.\n"
                        "- **Duplicates** — repeated keys, identical timestamps.\n"
                        "- **Already-sorted / reverse-sorted** — exposes order-dependent bugs.\n"
                        "- **Unicode and odd characters** — for any string-handling.\n"
                        "- **Concurrent access** — for shared state.\n"
                        "- **Failure modes** — disk full, network out, timeout.\n\n"
                        "The CtCI \"test a chess game\" problem (p. 154) is the canonical worked\n"
                        "example — read it once and the structure sticks."
                    ),
                    "key_takeaways": [
                        "Empty, single, extremes, duplicates, sorted/reversed — the eight-line checklist.",
                        "Add concurrency and failure modes for backend systems.",
                        "For string problems, always include Unicode and odd whitespace.",
                    ],
                },
            ],
        },
    ],
}


# ----------------------------------------------------- LeetCode problem sets ---
# High-level topic (module slug) -> the canonical LeetCode problems to drill it.
# Numbers and slugs are LeetCode's own. Attached to the track dict below so the
# seeder picks them up via module["problems"]. Work the lesson, then the list.
def _p(num: int, slug: str, title: str, difficulty: str, topic: str) -> dict:
    return {
        "leetcode_number": num,
        "leetcode_slug": slug,
        "title": title,
        "difficulty": difficulty,
        "topic": topic,
        "url": f"https://leetcode.com/problems/{slug}/",
    }


_CODING_PROBLEMS = {
    "arrays-and-strings": [
        _p(1, "two-sum", "Two Sum", "easy", "Hash table"),
        _p(242, "valid-anagram", "Valid Anagram", "easy", "Hashing / counting"),
        _p(125, "valid-palindrome", "Valid Palindrome", "easy", "Two pointers"),
        _p(121, "best-time-to-buy-and-sell-stock", "Best Time to Buy and Sell Stock", "easy", "Sliding window"),
        _p(49, "group-anagrams", "Group Anagrams", "medium", "Hashing"),
        _p(3, "longest-substring-without-repeating-characters", "Longest Substring Without Repeating Characters", "medium", "Sliding window"),
        _p(238, "product-of-array-except-self", "Product of Array Except Self", "medium", "Prefix products"),
        _p(11, "container-with-most-water", "Container With Most Water", "medium", "Two pointers"),
        _p(15, "3sum", "3Sum", "medium", "Two pointers / sorting"),
    ],
    "linked-lists": [
        _p(206, "reverse-linked-list", "Reverse Linked List", "easy", "Pointer surgery"),
        _p(21, "merge-two-sorted-lists", "Merge Two Sorted Lists", "easy", "Merge"),
        _p(141, "linked-list-cycle", "Linked List Cycle", "easy", "Runner / fast-slow"),
        _p(19, "remove-nth-node-from-end-of-list", "Remove Nth Node From End of List", "medium", "Runner technique"),
        _p(143, "reorder-list", "Reorder List", "medium", "Fast-slow + reverse"),
        _p(2, "add-two-numbers", "Add Two Numbers", "medium", "Carry / traversal"),
        _p(138, "copy-list-with-random-pointer", "Copy List with Random Pointer", "medium", "Hashing / interleave"),
        _p(146, "lru-cache", "LRU Cache", "medium", "Hash map + doubly linked list"),
    ],
    "stacks-and-queues": [
        _p(20, "valid-parentheses", "Valid Parentheses", "easy", "Stack"),
        _p(232, "implement-queue-using-stacks", "Implement Queue using Stacks", "easy", "Amortized two-stack"),
        _p(155, "min-stack", "Min Stack", "medium", "Auxiliary stack"),
        _p(150, "evaluate-reverse-polish-notation", "Evaluate Reverse Polish Notation", "medium", "Stack evaluation"),
        _p(739, "daily-temperatures", "Daily Temperatures", "medium", "Monotonic stack"),
        _p(84, "largest-rectangle-in-histogram", "Largest Rectangle in Histogram", "hard", "Monotonic stack"),
    ],
    "trees-and-graphs": [
        _p(104, "maximum-depth-of-binary-tree", "Maximum Depth of Binary Tree", "easy", "DFS"),
        _p(226, "invert-binary-tree", "Invert Binary Tree", "easy", "Tree recursion"),
        _p(102, "binary-tree-level-order-traversal", "Binary Tree Level Order Traversal", "medium", "BFS"),
        _p(98, "validate-binary-search-tree", "Validate Binary Search Tree", "medium", "BST invariant"),
        _p(235, "lowest-common-ancestor-of-a-binary-search-tree", "Lowest Common Ancestor of a BST", "medium", "BST traversal"),
        _p(230, "kth-smallest-element-in-a-bst", "Kth Smallest Element in a BST", "medium", "Inorder traversal"),
        _p(208, "implement-trie-prefix-tree", "Implement Trie (Prefix Tree)", "medium", "Trie"),
        _p(200, "number-of-islands", "Number of Islands", "medium", "Grid BFS/DFS"),
        _p(133, "clone-graph", "Clone Graph", "medium", "Graph traversal"),
        _p(207, "course-schedule", "Course Schedule", "medium", "Topological sort"),
        _p(297, "serialize-and-deserialize-binary-tree", "Serialize and Deserialize Binary Tree", "hard", "Tree (de)serialization"),
    ],
    "recursion-and-dp": [
        _p(70, "climbing-stairs", "Climbing Stairs", "easy", "1-D DP"),
        _p(198, "house-robber", "House Robber", "medium", "1-D DP"),
        _p(62, "unique-paths", "Unique Paths", "medium", "Grid DP"),
        _p(322, "coin-change", "Coin Change", "medium", "Unbounded knapsack"),
        _p(300, "longest-increasing-subsequence", "Longest Increasing Subsequence", "medium", "DP / patience"),
        _p(139, "word-break", "Word Break", "medium", "DP over strings"),
        _p(1143, "longest-common-subsequence", "Longest Common Subsequence", "medium", "2-D DP"),
        _p(39, "combination-sum", "Combination Sum", "medium", "Backtracking"),
        _p(78, "subsets", "Subsets", "medium", "Backtracking"),
        _p(72, "edit-distance", "Edit Distance", "medium", "2-D DP"),
    ],
    "sorting-and-searching": [
        _p(704, "binary-search", "Binary Search", "easy", "Binary search"),
        _p(34, "find-first-and-last-position-of-element-in-sorted-array", "Find First and Last Position of Element", "medium", "Binary search bounds"),
        _p(33, "search-in-rotated-sorted-array", "Search in Rotated Sorted Array", "medium", "Modified binary search"),
        _p(153, "find-minimum-in-rotated-sorted-array", "Find Minimum in Rotated Sorted Array", "medium", "Modified binary search"),
        _p(74, "search-a-2d-matrix", "Search a 2D Matrix", "medium", "Binary search"),
        _p(215, "kth-largest-element-in-an-array", "Kth Largest Element in an Array", "medium", "Quickselect / heap"),
        _p(56, "merge-intervals", "Merge Intervals", "medium", "Sort + sweep"),
        _p(4, "median-of-two-sorted-arrays", "Median of Two Sorted Arrays", "hard", "Binary search partition"),
    ],
    "object-oriented-design": [
        _p(706, "design-hashmap", "Design HashMap", "easy", "OOD / data structures"),
        _p(707, "design-linked-list", "Design Linked List", "medium", "OOD / data structures"),
        _p(622, "design-circular-queue", "Design Circular Queue", "medium", "OOD / ring buffer"),
        _p(1396, "design-underground-system", "Design Underground System", "medium", "OOD / hashing"),
    ],
    "bit-manipulation": [
        _p(136, "single-number", "Single Number", "easy", "XOR"),
        _p(191, "number-of-1-bits", "Number of 1 Bits", "easy", "Bit counting"),
        _p(338, "counting-bits", "Counting Bits", "easy", "DP + bits"),
        _p(190, "reverse-bits", "Reverse Bits", "easy", "Bit manipulation"),
        _p(268, "missing-number", "Missing Number", "easy", "XOR / Gauss sum"),
        _p(371, "sum-of-two-integers", "Sum of Two Integers", "medium", "Bitwise addition"),
    ],
}

# Append extra modules for CtCI chapters that weren't hand-authored above
# (Math/Logic, C/C++, Java, Databases, Threads/Locks, Moderate, Hard). These
# round out the track to all 17 CtCI chapters.
try:
    from .ctci_extra_modules import CTCI_EXTRA_MODULES
    TRACK_CODING["modules"].extend(CTCI_EXTRA_MODULES)
except ImportError:
    pass

# Attach LeetCode pointers and CtCI book problems to each module so the seeder
# picks them up under module["problems"] and module["ctci_problems"].
from .ctci_problems import CTCI_PROBLEMS_BY_MODULE
for _m in TRACK_CODING["modules"]:
    _m["problems"] = _CODING_PROBLEMS.get(_m["slug"], [])
    _m["ctci_problems"] = CTCI_PROBLEMS_BY_MODULE.get(_m["slug"], [])
