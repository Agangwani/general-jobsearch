"""Track 1 extension: lesson modules for CTCI chapters that weren't covered
in `coding.py`. Merged in by `coding.py` at module load time. Same shape
as the modules already in TRACK_CODING['modules']."""

CTCI_EXTRA_MODULES = [
    # ---------------------------------------------------------- M1.14
    {
        "slug": "math-and-logic-puzzles",
        "title": "Math and Logic Puzzles",
        "summary": (
            "Brainteasers, probability rules, and the four techniques McDowell uses "
            "to crack any puzzle — develop rules, balance the worst case, recognize "
            "patterns, and fall back on algorithm approaches."
        ),
        "source_refs": "CtCI Ch. 6, pp. 119–126",
        "est_minutes": 30,
        "lessons": [
            {
                "slug": "probability-rules",
                "title": "Probability rules from the chapter intro",
                "source_refs": "CtCI pp. 119–120",
                "body_md": (
                    "Most brainteasers boil down to two probability operations and one trap.\n\n"
                    "**Independence.** Two events A and B are independent if the outcome of one\n"
                    "tells you nothing about the other. Then `P(A and B) = P(A) * P(B)`. Coin\n"
                    "flips, dice rolls, and (usually) successive shots in a game are independent.\n\n"
                    "**Mutual exclusivity.** Two events are mutually exclusive if they can't both\n"
                    "happen. Then `P(A or B) = P(A) + P(B)`. \"Rolled a 6\" and \"rolled a 3\" on the\n"
                    "same die are mutually exclusive; \"rolled a 6\" and \"rolled an even number\"\n"
                    "are not — you have to subtract the overlap: `P(A or B) = P(A) + P(B) - P(A and B)`.\n\n"
                    "**The degenerate edge case McDowell calls out (p. 120):** if one or both\n"
                    "events has probability zero, the events are *both* independent *and*\n"
                    "mutually exclusive. That's a giveaway answer if an interviewer asks\n"
                    "\"can two events be both?\" — yes, when one is impossible.\n\n"
                    "When a problem mentions a probability `p` of a single trial repeated `n`\n"
                    "times, reach immediately for the binomial form: probability of exactly\n"
                    "`k` hits in `n` independent trials is `C(n, k) * p^k * (1-p)^(n-k)`."
                ),
                "key_takeaways": [
                    "Independent events: multiply. Mutually exclusive: add.",
                    "For overlap, subtract: P(A or B) = P(A) + P(B) - P(A and B).",
                    "A zero-probability event is both independent of and exclusive with any other.",
                ],
            },
            {
                "slug": "develop-rules-and-patterns",
                "title": "Develop rules and patterns",
                "source_refs": "CtCI pp. 121–122",
                "body_md": (
                    "McDowell's first technique (p. 121): when you discover a small useful fact\n"
                    "while solving a puzzle, **write it down as a numbered rule**, then combine\n"
                    "the rules.\n\n"
                    "The canonical example is the **two-rope problem**: \"two ropes each burn\n"
                    "for exactly one hour but unevenly — time exactly 15 minutes.\" Solving by\n"
                    "rules:\n\n"
                    "- **Rule 1.** Given a rope that burns in `x` minutes and another in `y`,\n"
                    "you can time `x + y` minutes (light one, then the other).\n"
                    "- **Rule 2.** Lighting *both ends* of a rope cuts its burn time in half —\n"
                    "you can time `x/2` minutes.\n"
                    "- **Rule 3.** Lighting rope 1 from both ends *while* rope 2 burns from\n"
                    "one end converts rope 2 into a rope of `y - x/2` minutes.\n\n"
                    "Composing them: light rope 1 from both ends and rope 2 from one end. When\n"
                    "rope 1 finishes (30 min), rope 2 has 30 min left — light its other end.\n"
                    "Rope 2 finishes 15 minutes later. Total: exactly 15 minutes.\n\n"
                    "The takeaway isn't the rope answer; it's the **habit of writing each\n"
                    "discovery as a reusable rule**. Puzzles compose. So do the rules."
                ),
                "key_takeaways": [
                    "Write each discovered fact as a numbered, reusable rule.",
                    "Combine rules — most puzzle solutions are compositions, not insights.",
                    "The two-rope problem is the worked example to internalize.",
                ],
            },
            {
                "slug": "worst-case-balancing",
                "title": "Worst-case shifting (balancing)",
                "source_refs": "CtCI pp. 122–123",
                "body_md": (
                    "Many brainteasers are framed as \"in the **fewest** uses of X, find Y.\"\n"
                    "When your first split gives a lopsided worst case, you can usually rebalance\n"
                    "by changing the split.\n\n"
                    "**The nine-balls problem (p. 122):** nine balls, one heavier; using a\n"
                    "balance scale only twice, find the heavy one.\n\n"
                    "Naive split — 4 vs. 4 with 1 aside:\n\n"
                    "- If they balance, the aside one is heavy (1 weighing — easy case).\n"
                    "- If not, you have 4 candidates and need *two more* weighings → 3 total.\n"
                    "- Worst case: 3. Too many.\n\n"
                    "Rebalanced split — 3 vs. 3 with 3 aside:\n\n"
                    "- One weighing tells you which group of 3 has the heavy ball.\n"
                    "- A second weighing on 1 vs. 1 (with 1 aside) finishes the job.\n"
                    "- Worst case: 2. Just right.\n\n"
                    "The trick: the original split was **too easy** in the easy case (1\n"
                    "weighing) at the cost of being too hard in the hard case. Shifting more\n"
                    "balls aside *balances* the cases. Whenever a worst-case bound feels just\n"
                    "out of reach, look for an imbalance like this."
                ),
                "key_takeaways": [
                    "If the easy case is cheap and the hard case is expensive, rebalance the split.",
                    "Nine balls: 3-3-3 beats 4-4-1 by tightening the worst case.",
                    "Generalizes: given N divisible by 3, one weighing isolates the heavy third.",
                ],
            },
            {
                "slug": "algorithm-approaches-for-puzzles",
                "title": "Algorithm approaches and useful math",
                "source_refs": "CtCI pp. 123, 629",
                "body_md": (
                    "When the puzzle resists rules and balancing, fall back on the same\n"
                    "**algorithm approaches** you'd use on a coding problem (p. 123).\n"
                    "McDowell calls out two as especially useful for puzzles:\n\n"
                    "- **Base Case and Build.** Solve for `n = 1`, then `n = 2`, look for the\n"
                    "pattern, and extend. \"Ants on a triangle\" and \"100 doors\" both yield.\n"
                    "- **Do It Yourself (DIY).** Work the problem on a small concrete example\n"
                    "by hand, then reverse-engineer what you did into an algorithm.\n\n"
                    "**Useful math (referenced as additional reading, p. 629).** Two facts\n"
                    "come up repeatedly:\n\n"
                    "- **Primality testing.** To check whether `n` is prime, trial-divide by\n"
                    "integers from 2 up to `√n`. Any composite must have a factor ≤ `√n`.\n"
                    "- **Sieve of Eratosthenes.** To list all primes up to `N`, start with a\n"
                    "boolean array of size `N+1` all true, then for each `i` from 2 upward,\n"
                    "if `i` is still marked prime, mark every multiple `2i, 3i, ...` composite.\n"
                    "Runs in `O(N log log N)`.\n\n"
                    "Brainteasers about factors, divisibility, or trailing zeros (problem 6.9,\n"
                    "16.5) reduce to applications of these two facts."
                ),
                "key_takeaways": [
                    "Base Case and Build, DIY — the two algorithm approaches that travel best to puzzles.",
                    "Trial division to √n is enough for primality.",
                    "Sieve of Eratosthenes enumerates all primes up to N in O(N log log N).",
                ],
            },
        ],
    },
    # ---------------------------------------------------------- M1.15
    {
        "slug": "c-and-cpp",
        "title": "C and C++",
        "summary": (
            "C++ memory model, classes and virtual functions, the vtable, and the "
            "interview pitfalls every C++ candidate gets quizzed on."
        ),
        "source_refs": "CtCI Ch. 12, pp. 159–164",
        "est_minutes": 30,
        "lessons": [
            {
                "slug": "memory-pointers-references",
                "title": "Memory, pointers, and references",
                "source_refs": "CtCI pp. 162–163",
                "body_md": (
                    "C and C++ expose the machine. Memory is yours to manage — and to leak.\n\n"
                    "**Pointers.** A pointer holds the **address** of a value. You can read,\n"
                    "write, or reassign the address. Two pointers can alias the same memory:\n\n"
                    "```\n"
                    "int * p = new int;\n"
                    "*p = 7;\n"
                    "int * q = p;     // q and p point to the same int\n"
                    "*p = 8;\n"
                    "cout << *q;      // prints 8\n"
                    "```\n\n"
                    "Pointer size depends on architecture: 4 bytes on 32-bit, 8 on 64-bit.\n"
                    "Interviewers love asking \"how much space does this struct take?\" — be\n"
                    "ready to add up the pointer widths.\n\n"
                    "**References.** A reference is an **alias** for an existing object. It\n"
                    "must be initialized at creation, cannot be null, and cannot be reseated.\n"
                    "Modifying the reference modifies the original:\n\n"
                    "```\n"
                    "int a = 5;\n"
                    "int & b = a;\n"
                    "b = 7;           // a is now 7\n"
                    "```\n\n"
                    "**Pointer arithmetic.** `p++` on a pointer advances by `sizeof(*p)` bytes,\n"
                    "not 1 byte. That's how array indexing works under the hood: `p[i]` is\n"
                    "sugar for `*(p + i)`."
                ),
                "key_takeaways": [
                    "Pointers store addresses; references are aliases that can't be null or reseated.",
                    "Pointer width depends on architecture (4 bytes 32-bit, 8 bytes 64-bit).",
                    "p++ advances by sizeof(*p), not by 1 — that's how arrays work.",
                ],
            },
            {
                "slug": "classes-inheritance-virtual",
                "title": "Classes, inheritance, and virtual functions",
                "source_refs": "CtCI pp. 159–161",
                "body_md": (
                    "C++ classes default to **private** members. Inheritance with `: public`\n"
                    "exposes the base's public interface. The constructor runs on creation, the\n"
                    "destructor on deletion — both are called automatically.\n\n"
                    "**The virtual-function gotcha (p. 160).** Without `virtual`, method calls\n"
                    "are bound at *compile time* (static binding):\n\n"
                    "```\n"
                    "Person * p = new Student();\n"
                    "p->aboutMe();   // prints \"I am a person\" — WRONG for OO intent\n"
                    "```\n\n"
                    "Mark `aboutMe()` as `virtual` in the base class and the call resolves at\n"
                    "*runtime* (dynamic binding) via the **vtable** — a per-class table of\n"
                    "function pointers that each instance carries an implicit pointer to.\n"
                    "Now `p->aboutMe()` correctly prints \"I am a student\".\n\n"
                    "**Pure virtual.** Writing `virtual bool addCourse(string s) = 0;` makes\n"
                    "`Person` an **abstract class** — it cannot be instantiated and subclasses\n"
                    "must implement `addCourse`.\n\n"
                    "**Virtual destructors (p. 161).** If a base-class pointer might point to a\n"
                    "subclass instance, the base destructor **must** be `virtual`. Otherwise\n"
                    "`delete p` only runs `~Person()` and leaks the `Student` portion. The\n"
                    "rule: any class meant to be inherited from should have a virtual\n"
                    "destructor."
                ),
                "key_takeaways": [
                    "Default access in a C++ class is private; in a struct it's public.",
                    "Non-virtual calls bind at compile time; virtual calls dispatch via the vtable.",
                    "Any base class meant for inheritance needs a virtual destructor or it leaks.",
                    "Pure virtual (= 0) makes a class abstract.",
                ],
            },
            {
                "slug": "cpp-interview-pitfalls",
                "title": "Common C++ interview pitfalls",
                "source_refs": "CtCI pp. 163–164",
                "body_md": (
                    "The questions interviewers love (and that CtCI 12.5–12.10 drill):\n\n"
                    "- **Shallow vs. deep copy (12.5).** A *shallow* copy duplicates the\n"
                    "pointer fields, so both objects share the pointee. A *deep* copy follows\n"
                    "every pointer and clones the underlying data. Default compiler-generated\n"
                    "copy constructors do shallow copies — a double-free disaster waiting to\n"
                    "happen. Override the copy constructor and `operator=` whenever you own\n"
                    "raw memory.\n\n"
                    "- **`malloc`/`free` vs. `new`/`delete`.** `malloc` returns raw bytes and\n"
                    "doesn't call constructors; `new` allocates *and* constructs. Mixing them\n"
                    "(\"malloc'd then delete\" or vice versa) is undefined behavior. Match\n"
                    "every `new` with `delete`, every `new[]` with `delete[]`, every `malloc`\n"
                    "with `free`.\n\n"
                    "- **Smart pointers (12.9).** A smart pointer wraps a raw pointer and uses\n"
                    "RAII (Resource Acquisition Is Initialization) — the destructor frees the\n"
                    "resource. Reference-counted smart pointers (`shared_ptr`) free the\n"
                    "underlying object when the count hits zero. This is the C++ answer to\n"
                    "Java's garbage collection.\n\n"
                    "- **`volatile` (12.6).** Tells the compiler \"this variable can change\n"
                    "outside the program's control\" (memory-mapped I/O, another thread,\n"
                    "signal handler) so it can't cache the value in a register.\n\n"
                    "Master shallow/deep copy and virtual destructors — those two questions\n"
                    "come up more than any others."
                ),
                "key_takeaways": [
                    "Default copy constructor is shallow — override it whenever you own raw memory.",
                    "Match new with delete, new[] with delete[], malloc with free. Never mix.",
                    "Smart pointers + RAII are the idiomatic answer to manual memory management.",
                    "volatile prevents the compiler from caching a variable in a register.",
                ],
            },
        ],
    },
    # ---------------------------------------------------------- M1.16
    {
        "slug": "java",
        "title": "Java",
        "summary": (
            "Java language trivia interviewers actually ask: collections, "
            "generics-by-erasure, reflection, lambdas, and the final/finally/finalize "
            "trio."
        ),
        "source_refs": "CtCI Ch. 13, pp. 165–168",
        "est_minutes": 30,
        "lessons": [
            {
                "slug": "java-collections",
                "title": "Collections framework essentials",
                "source_refs": "CtCI pp. 166–167",
                "body_md": (
                    "Four collections cover ~90% of Java interview code:\n\n"
                    "- **`ArrayList<T>`** — dynamically resizing array. `O(1)` amortized\n"
                    "append, `O(1)` index-based get, `O(n)` insert/delete in the middle.\n"
                    "Default choice for a list.\n"
                    "- **`Vector<T>`** — same as `ArrayList` but **synchronized** on every\n"
                    "method. Almost never the right pick today; use `ArrayList` with explicit\n"
                    "locks if you need thread safety.\n"
                    "- **`LinkedList<T>`** — Java's doubly-linked list. `O(1)` insert/delete\n"
                    "at the ends, `O(n)` lookup. Mostly useful as a `Deque`.\n"
                    "- **`HashMap<K, V>`** — `O(1)` average lookup and insert. Keys are\n"
                    "iterated in **no guaranteed order**. Backed by an array of buckets, each\n"
                    "a linked list (or, since Java 8, a tree once the bucket grows past a\n"
                    "threshold).\n\n"
                    "Two HashMap cousins the chapter (13.5) drills:\n\n"
                    "- **`TreeMap`** — `O(log n)` lookup/insert, keys iterated in **sorted**\n"
                    "order. Backed by a red-black tree. Requires keys implement `Comparable`.\n"
                    "Use when you need ranged or sorted access.\n"
                    "- **`LinkedHashMap`** — `O(1)` lookup/insert, keys iterated in\n"
                    "**insertion** order. Backed by buckets plus a doubly-linked spine. Use\n"
                    "for LRU caches and for any time you need stable iteration order.\n\n"
                    "Rule of thumb: reach for `HashMap` unless you specifically need\n"
                    "ordering (then `LinkedHashMap` or `TreeMap`)."
                ),
                "key_takeaways": [
                    "ArrayList is the default list; LinkedList is mostly a Deque.",
                    "HashMap: O(1) average, unordered. TreeMap: O(log n), sorted. LinkedHashMap: O(1), insertion-ordered.",
                    "Vector is synchronized — almost never what you want today.",
                ],
            },
            {
                "slug": "generics-vs-templates",
                "title": "Generics vs. templates (type erasure)",
                "source_refs": "CtCI pp. 167, 433–435",
                "body_md": (
                    "Java generics and C++ templates *look* alike (`List<String>`,\n"
                    "`vector<string>`) but the implementations are wildly different (13.4).\n\n"
                    "**Java generics use type erasure.** At compile time the compiler erases\n"
                    "the type parameter and inserts casts. So:\n\n"
                    "```\n"
                    "Vector<String> v = new Vector<String>();\n"
                    "v.add(\"hello\");\n"
                    "String s = v.get(0);\n"
                    "```\n\n"
                    "becomes, after compilation:\n\n"
                    "```\n"
                    "Vector v = new Vector();\n"
                    "v.add(\"hello\");\n"
                    "String s = (String) v.get(0);\n"
                    "```\n\n"
                    "Consequences: there is only **one** class file per generic class. All\n"
                    "`MyClass<Foo>` and `MyClass<Bar>` instances share static fields. You\n"
                    "can't use primitives as type parameters (must box: `Integer`, not `int`).\n"
                    "You can't instantiate a `T` (`new T()` doesn't compile). Generics are\n"
                    "sometimes called **\"syntactic sugar\"** for this reason.\n\n"
                    "**C++ templates duplicate at compile time.** The compiler generates a\n"
                    "fresh class for each type used (`MyClass<int>`, `MyClass<string>` are\n"
                    "*different* classes), so static fields are *not* shared, primitives work\n"
                    "fine, and you can instantiate `T`. The tradeoff: bigger binaries and\n"
                    "longer compiles.\n\n"
                    "Interview soundbite: **\"Generics are erased at runtime; templates are\n"
                    "duplicated at compile time.\"**"
                ),
                "key_takeaways": [
                    "Java generics use type erasure; templates use code generation.",
                    "Java: one class per generic, no primitives, can't new T(), static is shared.",
                    "C++: one class per type parameter, primitives fine, can new T, static is per type.",
                ],
            },
            {
                "slug": "java-language-trivia",
                "title": "final / finally / finalize, reflection, and lambdas",
                "source_refs": "CtCI pp. 167–168, 433–438",
                "body_md": (
                    "**final / finally / finalize (13.3).** Three different things that\n"
                    "share a prefix.\n\n"
                    "- **`final`** controls *changeability*. On a primitive variable: value\n"
                    "can't change. On a reference variable: can't reseat (the object can\n"
                    "still mutate). On a method: can't be overridden. On a class: can't be\n"
                    "subclassed.\n"
                    "- **`finally`** is a `try`/`catch` clause that runs *after* try and catch\n"
                    "no matter what — even if `try` had a `return`. The exceptions: the JVM\n"
                    "exits, or the thread is killed.\n"
                    "- **`finalize()`** is a method on `Object` that the garbage collector\n"
                    "calls *just before* destroying an unreachable object. Last-resort\n"
                    "cleanup; rarely needed and discouraged in modern Java.\n\n"
                    "**Object reflection (13.6).** Reflection lets code inspect classes,\n"
                    "fields, and methods *at runtime* — get a `Class` by name, list its\n"
                    "methods, construct instances, invoke methods by string name. Three uses:\n"
                    "introspection (debuggers, IDEs), dynamic dispatch (frameworks like\n"
                    "Spring, JUnit), and serialization (Jackson, Gson). The cost: slower than\n"
                    "direct calls and bypasses access modifiers.\n\n"
                    "**Lambda expressions (13.7).** Java 8 added the arrow syntax\n"
                    "`country -> country.getContinent().equals(c)` and the stream API. Common\n"
                    "pattern: `list.stream().filter(predicate).map(fn).reduce(...)`. Lambdas\n"
                    "are just instances of single-abstract-method (\"functional\") interfaces\n"
                    "like `Predicate<T>`, `Function<T,R>`, `Comparator<T>`."
                ),
                "key_takeaways": [
                    "final = unchangeable, finally = always runs, finalize() = pre-GC hook.",
                    "Reflection: runtime introspection. Powerful for frameworks; slow and unsafe at scale.",
                    "Lambdas are instances of single-method interfaces (Predicate, Function, etc.).",
                ],
            },
        ],
    },
    # ---------------------------------------------------------- M1.17
    {
        "slug": "databases",
        "title": "Databases",
        "summary": (
            "SQL joins, normalization tradeoffs, and how to design a small "
            "relational schema from a vague \"design a database for X\" prompt."
        ),
        "source_refs": "CtCI Ch. 14, pp. 169–172",
        "est_minutes": 30,
        "lessons": [
            {
                "slug": "joins",
                "title": "Joins: inner, left, right, full, cross",
                "source_refs": "CtCI pp. 169, 442–443",
                "body_md": (
                    "A `JOIN` combines rows from two tables matched on a key. The flavor\n"
                    "determines what happens to unmatched rows. Imagine two tables:\n"
                    "**Regular** (BUDWEISER, COCACOLA, PEPSI) and **CalorieFree** (Diet\n"
                    "Coke = COCACOLA, Fresca = FRESCA, Diet Pepsi = PEPSI, Pepsi Light =\n"
                    "PEPSI, Water = WATER).\n\n"
                    "- **`INNER JOIN`** — only rows where the key exists in **both**.\n"
                    "Result: 3 rows (the COCACOLA match, plus two PEPSI matches).\n"
                    "```\n"
                    "SELECT r.Name, cf.Name\n"
                    "FROM Regular r INNER JOIN CalorieFree cf ON r.Code = cf.Code;\n"
                    "```\n"
                    "- **`LEFT OUTER JOIN`** (or just `LEFT JOIN`) — all rows from the left\n"
                    "table; unmatched right-side columns are `NULL`. Result: 4 rows (INNER\n"
                    "+ BUDWEISER with `NULL` on the right).\n"
                    "- **`RIGHT OUTER JOIN`** — mirror image. All rows from the right;\n"
                    "unmatched left-side columns are `NULL`. Result: 5 rows (INNER + FRESCA,\n"
                    "WATER with `NULL` on the left). Note that `A LEFT JOIN B` ≡ `B RIGHT JOIN A`.\n"
                    "- **`FULL OUTER JOIN`** — union of LEFT and RIGHT. Every row from both\n"
                    "tables; `NULL` wherever no match. Result: 6 rows.\n"
                    "- **`CROSS JOIN`** — Cartesian product. Every row of A paired with every\n"
                    "row of B. No `ON` clause. Use sparingly.\n\n"
                    "In interviews, when you need to count things that may be zero (\"students\n"
                    "with no enrolled course\"), reach for `LEFT JOIN` — `INNER JOIN` will\n"
                    "silently drop them."
                ),
                "key_takeaways": [
                    "INNER = both sides match. LEFT/RIGHT = keep all of one side, NULL the other.",
                    "FULL OUTER = union of LEFT and RIGHT. CROSS = Cartesian product.",
                    "Counting items that may be zero? Use LEFT JOIN, not INNER.",
                ],
            },
            {
                "slug": "normalization-vs-denormalization",
                "title": "Normalization vs. denormalization",
                "source_refs": "CtCI pp. 169, 172, 443–444",
                "body_md": (
                    "**Normalized** schemas (14.5) minimize redundancy. Each fact is stored\n"
                    "once and referenced by foreign key. A `Courses` table stores `TeacherID`\n"
                    "and a separate `Teachers` table stores the teacher's name and address.\n"
                    "Updates are cheap (change a name in one place) but reads require joins.\n\n"
                    "**Denormalized** schemas duplicate data on purpose to dodge joins. The\n"
                    "teacher's name is copied into the `Courses` row. Reads are fast — no\n"
                    "join — but updates have to touch every copy, and rows can drift out of\n"
                    "sync.\n\n"
                    "**Trade-offs (p. 443):**\n\n"
                    "Pros of denormalization:\n\n"
                    "- Retrieving data is faster (fewer joins).\n"
                    "- Queries to retrieve are simpler and less bug-prone.\n\n"
                    "Cons of denormalization:\n\n"
                    "- Updates and inserts are more expensive and harder to write correctly.\n"
                    "- Data can become inconsistent — \"which copy is the right one?\"\n"
                    "- More storage required.\n\n"
                    "**Reality (p. 444):** large-scale systems use *both*. Normalize the\n"
                    "transactional store; denormalize read-heavy paths and analytics tables.\n"
                    "The CtCI rule of thumb: \"joins are slow at scale, so denormalize the\n"
                    "data you read often.\""
                ),
                "key_takeaways": [
                    "Normalized: one copy of each fact. Denormalized: redundant copies for fast reads.",
                    "Denormalize when read latency matters more than write cost and storage.",
                    "Real systems blend both: normalized OLTP, denormalized analytics/serving.",
                ],
            },
            {
                "slug": "small-database-design",
                "title": "Designing a small schema from scratch",
                "source_refs": "CtCI pp. 171–172",
                "body_md": (
                    "When asked to \"design a database for a rental agency / a school / a\n"
                    "library,\" McDowell prescribes four steps (pp. 171–172):\n\n"
                    "1. **Handle ambiguity.** Database questions are intentionally vague.\n"
                    "Clarify scope before you draw any tables. \"One location or many?\"\n"
                    "\"Can a tenant rent two apartments?\" Some rare cases are better handled\n"
                    "as workarounds (duplicate the contact info) than as schema features.\n\n"
                    "2. **Define the core objects.** Each becomes a table. For a rental\n"
                    "agency: `Property`, `Building`, `Apartment`, `Tenant`, `Manager`.\n\n"
                    "3. **Analyze relationships.** Are they one-to-many or many-to-many?\n"
                    "One-to-many usually goes as a foreign key (`Apartments` has a\n"
                    "`BuildingID`). Many-to-many needs a **junction table**: a\n"
                    "`TenantApartments` table with `(TenantID, ApartmentID)` is how you\n"
                    "model \"tenants can rent multiple apartments, apartments can have\n"
                    "multiple tenants.\"\n\n"
                    "4. **Investigate actions.** Walk through common operations (lease,\n"
                    "move-out, payment) and check the schema supports them efficiently.\n"
                    "Each new action often surfaces a missing table or column.\n\n"
                    "**Entity-Relationship diagrams (14.6)** are the standard sketch. Boxes\n"
                    "are entities (`Person`, `Company`), diamonds are relationships\n"
                    "(`WorksFor`), with cardinality on the edges. \"ISA\" arrows model\n"
                    "inheritance — a `Professional` ISA `Person`."
                ),
                "key_takeaways": [
                    "Handle ambiguity first — clarify scope before drawing any tables.",
                    "Many-to-many always needs a junction table; one-to-many uses a foreign key.",
                    "ER diagrams: entities are boxes, relationships are diamonds, ISA arrows are inheritance.",
                ],
            },
        ],
    },
    # ---------------------------------------------------------- M1.18
    {
        "slug": "threads-and-locks",
        "title": "Threads and Locks",
        "summary": (
            "Threads, synchronization primitives, and the four conditions every "
            "deadlock requires — anchored to McDowell's dining-philosophers example."
        ),
        "source_refs": "CtCI Ch. 15, pp. 173–178",
        "est_minutes": 30,
        "lessons": [
            {
                "slug": "thread-vs-process",
                "title": "Thread vs. process and context switching",
                "source_refs": "CtCI pp. 173–174",
                "body_md": (
                    "A **process** is a running instance of a program with its own\n"
                    "**address space**, file descriptors, and OS resources. Two processes\n"
                    "are isolated by default — to share data they need IPC (pipes,\n"
                    "shared memory, sockets).\n\n"
                    "A **thread** is a unit of execution that lives *inside* a process.\n"
                    "All threads in a process **share the same heap** (and file\n"
                    "descriptors); each gets its own stack and register state. That sharing\n"
                    "is what makes threads cheap to communicate but dangerous: any write to\n"
                    "shared memory races against every other read.\n\n"
                    "**Threads in Java (p. 173).** Two ways to create one:\n\n"
                    "- Implement `Runnable`, pass the instance to `new Thread(r)`, call\n"
                    "`start()`. Preferred because Java lacks multiple inheritance — your\n"
                    "class can still extend something else.\n"
                    "- Extend `Thread` and override `run()`. Simpler but locks up your one\n"
                    "inheritance slot.\n\n"
                    "**Context switch (15.2).** The OS swaps one thread off the CPU and\n"
                    "another on. It saves the outgoing thread's registers and program\n"
                    "counter, loads the incoming thread's, and possibly flushes the TLB.\n"
                    "Switching between threads of the *same* process is cheap (shared\n"
                    "address space); switching between processes is expensive (TLB flush,\n"
                    "cache cold). A context switch typically costs a few microseconds —\n"
                    "an eternity at modern CPU speeds."
                ),
                "key_takeaways": [
                    "Process = isolated address space. Thread = execution unit sharing the process heap.",
                    "Threads in Java: prefer implementing Runnable to extending Thread.",
                    "Context switching across processes costs more than across threads (TLB flush).",
                ],
            },
            {
                "slug": "synchronization-primitives",
                "title": "synchronized, locks, and semaphores",
                "source_refs": "CtCI pp. 175–177",
                "body_md": (
                    "Shared memory means race conditions. Java's primitives:\n\n"
                    "- **`synchronized` method** (p. 175). Acquires an *implicit* lock on\n"
                    "the receiver object (`this`) for the duration of the call. Two threads\n"
                    "calling a `synchronized` method on the **same instance** block each\n"
                    "other; on different instances they run freely. `static synchronized`\n"
                    "locks on the `Class` object instead.\n\n"
                    "- **`synchronized(obj) { ... }` block.** Same semantics as a synchronized\n"
                    "method but on an arbitrary lock object. Useful when you want to\n"
                    "synchronize only part of a method, or on a lock object distinct from\n"
                    "`this`.\n\n"
                    "- **Explicit `Lock`** (p. 176, e.g. `ReentrantLock`). Call `lock()`\n"
                    "before the critical section and `unlock()` after. More flexible than\n"
                    "`synchronized` — supports `tryLock`, timeouts, lock ordering. Pair it\n"
                    "with `try { } finally { lock.unlock(); }` so exceptions can't strand\n"
                    "the lock.\n\n"
                    "- **Semaphores.** A counter you decrement on `acquire()` and\n"
                    "increment on `release()`. A semaphore with count `1` is essentially a\n"
                    "mutex; counts > 1 throttle to N concurrent users (connection pools,\n"
                    "rate limiters).\n\n"
                    "The example McDowell walks (p. 176): a `LockedATM` with `withdraw`\n"
                    "and `deposit` methods that both acquire the same `Lock` — without it,\n"
                    "interleaved reads of `balance` lose updates."
                ),
                "key_takeaways": [
                    "synchronized method locks on `this`; static synchronized locks on Class.",
                    "Explicit Locks are more flexible — use them with try/finally to guarantee unlock.",
                    "Semaphore count = 1 is a mutex; count > 1 throttles concurrent users.",
                ],
            },
            {
                "slug": "deadlock-prevention",
                "title": "Deadlock and the four Coffman conditions",
                "source_refs": "CtCI pp. 177–178",
                "body_md": (
                    "**Deadlock** is when threads block each other forever waiting on\n"
                    "locks. McDowell formalizes the **four conditions that must all hold**\n"
                    "for deadlock (p. 177) — known as the Coffman conditions:\n\n"
                    "1. **Mutual exclusion** — a resource can be held by only one thread\n"
                    "at a time.\n"
                    "2. **Hold and wait** — a thread that already holds a resource is\n"
                    "allowed to request more without releasing what it has.\n"
                    "3. **No preemption** — the OS can't forcibly take a resource away\n"
                    "from the thread holding it.\n"
                    "4. **Circular wait** — there's a cycle of threads where each is\n"
                    "waiting on the next.\n\n"
                    "Break **any one** and you've prevented deadlock. Most real systems\n"
                    "attack #4 by **imposing a global lock ordering** — every thread\n"
                    "acquires locks in the same total order, so the cycle can't form.\n\n"
                    "**Dining Philosophers (15.3, p. 177–178).** Five philosophers sit\n"
                    "around a table with one chopstick between each pair. Each needs both\n"
                    "neighbors' chopsticks to eat and always grabs the left first. If they\n"
                    "all grab simultaneously, every philosopher holds their left chopstick\n"
                    "waiting on their right — classic circular wait.\n\n"
                    "Fixes that break a condition:\n\n"
                    "- **Order the chopsticks** (lock ordering): philosopher i picks up the\n"
                    "lower-numbered chopstick first. Now one philosopher reaches for\n"
                    "right-then-left and the cycle is broken.\n"
                    "- **`tryLock` with backoff** (break hold-and-wait): if the second\n"
                    "chopstick is unavailable, release the first and retry.\n"
                    "- **Cap diners at 4** (semaphore counting): with at most 4 of 5\n"
                    "philosophers seated, at least one chopstick is always free."
                ),
                "key_takeaways": [
                    "Coffman: mutual exclusion + hold-and-wait + no preemption + circular wait → deadlock.",
                    "Break any one condition to prevent deadlock; lock ordering attacks circular wait.",
                    "Dining philosophers: order the chopsticks or use tryLock with backoff.",
                ],
            },
        ],
    },
    # ---------------------------------------------------------- M1.19
    {
        "slug": "ctci-moderate",
        "title": "Moderate Problems (CtCI Ch. 16)",
        "summary": (
            "How to approach a CtCI moderate problem and the patterns that recur. "
            "This module's real value lives in the 26 problems themselves — work the "
            "problem detail pages."
        ),
        "source_refs": "CtCI Ch. 16, pp. 181–185",
        "est_minutes": 20,
        "lessons": [
            {
                "slug": "approaching-a-moderate-problem",
                "title": "How to approach a CtCI moderate problem",
                "source_refs": "CtCI Ch. 16 intro; framework from Ch. VII, pp. 60–81",
                "body_md": (
                    "CtCI's moderate chapter has no separate intro — it dives straight\n"
                    "into 26 problems. The approach is the same five-step framework from\n"
                    "earlier (Ch. VII), but the problems are tuned to test *which step\n"
                    "you're best at skipping*:\n\n"
                    "1. **Listen carefully.** Moderate problems hide constraints in\n"
                    "innocent-looking words. \"Without temporary variables\" (16.1) means\n"
                    "*bitwise tricks*. \"You may not use comparison operators\" (16.7)\n"
                    "means *arithmetic identities and bit hacks*. \"In place\" rules out\n"
                    "extra structures.\n\n"
                    "2. **Build a real example.** For numeric problems (16.5 trailing zeros,\n"
                    "16.6 smallest difference, 16.10 living people) reach for an example\n"
                    "with both edge cases (zeros, duplicates, negatives) and ordinary\n"
                    "values. A symmetric example will hide bugs.\n\n"
                    "3. **State the brute force out loud.** McDowell emphasizes (p. 77)\n"
                    "that even if it's `O(n³)`, say it. Then apply **BUD** — Bottlenecks,\n"
                    "Unnecessary work, Duplicated work — to optimize. Most moderate\n"
                    "problems have a quadratic brute force and a linear or `n log n`\n"
                    "real answer.\n\n"
                    "4. **Watch the time budget.** A moderate problem in a 45-minute\n"
                    "interview is one of two; you have ~20–25 minutes including writing\n"
                    "and testing. If a 10-minute optimization isn't appearing, code the\n"
                    "brute force and move on.\n\n"
                    "The big mental shift: at this tier you're expected to *finish*. Code\n"
                    "completeness and tests matter more than a clever trick."
                ),
                "key_takeaways": [
                    "Five-step framework applies; moderate problems test which step you skip.",
                    "Hidden phrases like \"no temp variables\" or \"no comparisons\" are constraint hints.",
                    "Brute force + BUD beats hunting for a clever trick under time pressure.",
                ],
            },
            {
                "slug": "moderate-patterns-to-recognize",
                "title": "Common moderate-tier patterns",
                "source_refs": "CtCI pp. 181–185 (problems 16.1–16.26)",
                "body_md": (
                    "Walking the 26 problems, six pattern families dominate:\n\n"
                    "- **Bit and arithmetic tricks** — 16.1 number swap (XOR), 16.7 max\n"
                    "without `if`, 16.9 arithmetic via add only. Recognize the constraint\n"
                    "language and reach for XOR, bit shifts, sign-bit isolation.\n\n"
                    "- **Number-base and digit tricks** — 16.5 trailing zeros (count\n"
                    "factors of 5), 16.8 English-int conversion. These reduce to\n"
                    "manipulating digit groups and prime factorizations.\n\n"
                    "- **Geometric problems** — 16.3 line-segment intersection, 16.13\n"
                    "bisect two squares, 16.14 best line through points. Solve with\n"
                    "coordinate geometry: parameterize lines, watch for vertical-line edge\n"
                    "cases, hash slopes carefully with float tolerance.\n\n"
                    "- **Simulation / state machines** — 16.4 tic-tac-toe win check,\n"
                    "16.15 Mastermind hits, 16.22 Langton's ant. The trick is choosing the\n"
                    "right *data structure* for the state (hash set of visited cells, two\n"
                    "passes for hits vs. pseudo-hits).\n\n"
                    "- **Multi-pass / two-pointer scans** — 16.6 smallest difference (sort,\n"
                    "then linear sweep), 16.16 sub-sort, 16.17 max contiguous subarray\n"
                    "(Kadane), 16.24 pairs with sum. The brute force is `O(n²)`; the\n"
                    "linear/`n log n` win comes from sorting or a hash set.\n\n"
                    "- **Design + LRU / caches** — 16.25 LRU cache. Hash map + doubly\n"
                    "linked list is the canonical solution.\n\n"
                    "If you can name the pattern within 30 seconds of reading a problem,\n"
                    "you're already most of the way to the optimum."
                ),
                "key_takeaways": [
                    "Six pattern families: bit tricks, digit/base, geometry, simulation, two-pointer, design.",
                    "Naming the pattern fast is half the optimization.",
                    "Two-pointer or hash set is the usual O(n²) → O(n) escape route.",
                ],
            },
        ],
    },
    # ---------------------------------------------------------- M1.20
    {
        "slug": "ctci-hard",
        "title": "Hard Problems (CtCI Ch. 17)",
        "summary": (
            "Recognizing when you're in a CtCI hard problem and the techniques that "
            "crack them. Like the moderate module, the real value is in the 26 "
            "problems — work the problem detail pages."
        ),
        "source_refs": "CtCI Ch. 17, pp. 186–190",
        "est_minutes": 20,
        "lessons": [
            {
                "slug": "recognizing-a-hard-problem",
                "title": "Recognizing you're in a hard problem",
                "source_refs": "CtCI Ch. 17 intro and problem set",
                "body_md": (
                    "CtCI's hard chapter also has no separate prose intro, but the\n"
                    "problems share unmistakable **red flags** worth learning to spot:\n\n"
                    "- **The brute force isn't obvious.** Easy and moderate problems have\n"
                    "a brute force you can state in 30 seconds (\"try every pair\"). For\n"
                    "17.4 missing number in `O(n)` with bit-level access, 17.7 baby-name\n"
                    "synonyms, 17.13 re-spacing a document — even *stating* a baseline\n"
                    "takes thought.\n\n"
                    "- **Strange operations or constraints.** 17.1 add without `+`,\n"
                    "17.10 majority in `O(n)` time and `O(1)` space, 17.4 \"only\n"
                    "operation is fetch the jth bit of A[i].\" When the problem invents a\n"
                    "primitive, the solution exploits exactly that primitive.\n\n"
                    "- **A clever insight required.** 17.5 longest balanced letter/number\n"
                    "subarray (prefix-sum-as-key trick), 17.6 count of 2s from 0 to n\n"
                    "(digit-by-digit analytics), 17.8 circus tower (LIS in two\n"
                    "dimensions). You're not going to brute-force optimize your way\n"
                    "there — there's a *trick*.\n\n"
                    "- **You're still circling after 5 minutes.** If you haven't even\n"
                    "stated a brute force after a few minutes, you're in hard territory.\n"
                    "Don't keep silent — narrate what you've ruled out, ask for a hint,\n"
                    "or pivot to a smaller subproblem you *can* solve.\n\n"
                    "Knowing you're in a hard problem is itself the signal to slow down,\n"
                    "draw more examples, and look for an invariant rather than an\n"
                    "algorithm."
                ),
                "key_takeaways": [
                    "Hard problems flag themselves: non-obvious brute force, weird primitives, clever-insight feel.",
                    "If you can't even state a brute force in 5 minutes, you're in hard territory.",
                    "Slow down, draw more examples, look for an invariant — not an algorithm.",
                ],
            },
            {
                "slug": "hard-problem-techniques",
                "title": "Techniques that crack hard problems",
                "source_refs": "CtCI pp. 186–190 (problems 17.1–17.26)",
                "body_md": (
                    "Across the 26 hard problems, five techniques recur:\n\n"
                    "- **Bit-level reformulation.** 17.1 add without `+` uses carry-and-XOR.\n"
                    "17.4 missing number reduces to summing one bit at a time. When the\n"
                    "constraint forbids arithmetic, the answer is almost always bits.\n\n"
                    "- **Mathematical reformulation.** 17.6 count of 2s analyzes the\n"
                    "problem digit by digit; 17.9 kth multiple of {3,5,7} reframes the\n"
                    "search as a min-heap over a generated lattice; 17.13 re-space the\n"
                    "document uses DP over the suffix. The lesson: a hard combinatorial\n"
                    "question often has a clean recurrence hiding inside it.\n\n"
                    "- **Augmented data structures.** 17.8 circus tower = sort by height,\n"
                    "LIS on weight (`O(n log n)`). 17.20 continuous median = two heaps\n"
                    "(min-heap of the upper half, max-heap of the lower). 17.24 max\n"
                    "submatrix = 1-D Kadane plus a clever sum prefix. When raw data won't\n"
                    "give you `O(n log n)`, augment it.\n\n"
                    "- **Binary search the answer space.** When the answer is monotone in\n"
                    "some parameter (\"smallest K such that ...\") binary search the\n"
                    "*parameter*. Doesn't appear by name in Ch. 17 problems, but it's the\n"
                    "standard hard-problem unlock and the obvious sibling of 17.10's\n"
                    "linear-time scan.\n\n"
                    "- **Randomization.** 17.2 shuffle a deck (Fisher-Yates), 17.3 random\n"
                    "set of m from n (reservoir sampling). When uniform random over\n"
                    "exponentially many outcomes is the goal, the answer is incremental:\n"
                    "swap-with-random-prefix or replace-with-probability-k/i.\n\n"
                    "Master the first three — bit reformulation, math reformulation, and\n"
                    "augmented structures — and you'll solve roughly 80% of the chapter."
                ),
                "key_takeaways": [
                    "Bit reformulation answers \"no arithmetic\" constraints; math reformulation answers digit/combinatorial ones.",
                    "Augmented structures (two heaps, sort-then-LIS, prefix sums) get you the missing log factor.",
                    "Randomization handles uniform-over-many-outcomes (shuffle, reservoir).",
                    "Binary search the *answer space* when the answer is monotone in a parameter.",
                ],
            },
        ],
    },
]
