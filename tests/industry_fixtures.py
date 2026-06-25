"""Industry resume fixtures — the manifest behind the comprehensive, multi-industry
test suite (tests/test_industry_resumes.py).

Twenty synthetic-but-realistic resumes, one per major New York City industry
(ranked from NYC EDC "State of the Economy", NY DOL "Significant Industries",
and BLS OEWS). Each entry pins:

- the resume file (tests/fixtures/resumes/*.txt),
- the occupation the role-targeter is expected to match it to,
- the prep "discipline" the resume should surface (see jobsearch/prep/disciplines.py),
- a representative NYC employer + a representative posting for that industry,
  used to prove company discovery and fit-scoring tailor *per resume* (different
  resumes must not all surface the same companies / jobs).

The company/posting text is deliberately industry-distinct so TF-IDF ranking can
tell them apart — that is the whole point of the "no homogeneity" tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

RESUME_DIR = Path(__file__).resolve().parent / "fixtures" / "resumes"


@dataclass(frozen=True)
class IndustryFixture:
    slug: str                 # short id, matches the resume filename stem
    industry: str             # human-readable industry name
    resume_file: str          # filename under fixtures/resumes/
    expected_occupation: str  # the occupation build_profile should rank #1
    discipline: str           # prep discipline this resume should surface
    own_title: str            # a posting title that SHOULD match its own profile
    company: str              # a representative NYC employer in the industry
    company_titles: tuple[str, ...]   # roles that employer is hiring for
    company_snippet: str      # role/JD evidence text (drives lead ranking)
    job_title: str            # representative posting title
    job_description: str      # representative posting body (drives fit scoring)

    @property
    def path(self) -> Path:
        return RESUME_DIR / self.resume_file

    def resume_text(self) -> str:
        return self.path.read_text()


FIXTURES: tuple[IndustryFixture, ...] = (
    IndustryFixture(
        slug="financial-services",
        industry="Financial Services (Banking & Capital Markets)",
        resume_file="01-financial-services.txt",
        expected_occupation="Investment Banking / Capital Markets",
        discipline="finance",
        own_title="Investment Banking Analyst",
        company="Lazard",
        company_titles=("Investment Banking Analyst", "M&A Associate"),
        company_snippet=("Execute M&A and capital markets transactions; build DCF, LBO, "
                         "and comparable companies valuation models and pitch books."),
        job_title="Investment Banking Analyst, M&A",
        job_description=("Join our mergers and acquisitions group to build DCF and LBO "
                         "valuation models, draft pitch books and CIMs, and run due "
                         "diligence on buy-side and sell-side capital markets deals."),
    ),
    IndustryFixture(
        slug="healthcare",
        industry="Healthcare",
        resume_file="02-healthcare.txt",
        expected_occupation="Registered Nurse",
        discipline="healthcare",
        own_title="Registered Nurse, ICU",
        company="NewYork-Presbyterian",
        company_titles=("Registered Nurse", "Charge Nurse"),
        company_snippet=("Provide critical patient care in an acute care unit; medication "
                         "administration, care plans, and Epic EHR documentation."),
        job_title="Registered Nurse - Medical ICU",
        job_description=("Deliver direct patient care for critically ill patients: "
                         "assessment, medication administration, care plans, triage, and "
                         "Epic EHR charting. BLS and ACLS required."),
    ),
    IndustryFixture(
        slug="technology",
        industry="Technology / Software",
        resume_file="03-technology.txt",
        expected_occupation="Software Engineer",
        discipline="software",
        own_title="Senior Software Engineer, Backend",
        company="Datadog",
        company_titles=("Senior Software Engineer", "Backend Engineer"),
        company_snippet=("Build distributed backend services in Go and Python, Kafka "
                         "pipelines, and high-scale observability infrastructure on AWS."),
        job_title="Senior Software Engineer, Distributed Systems",
        job_description=("Design and operate distributed microservices in Go and Python on "
                         "Kubernetes and AWS, processing millions of events with Kafka. "
                         "Own services end to end including on-call."),
    ),
    IndustryFixture(
        slug="consulting",
        industry="Management Consulting",
        resume_file="04-consulting.txt",
        expected_occupation="Management Consultant",
        discipline="consulting",
        own_title="Management Consultant",
        company="McKinsey & Company",
        company_titles=("Management Consultant", "Engagement Manager"),
        company_snippet=("Advise executives on corporate strategy and digital "
                         "transformation; structure ambiguous problems and build business cases."),
        job_title="Strategy Consultant - Engagement Manager",
        job_description=("Lead client engagements on corporate strategy and operating-model "
                         "transformation. Structure problems, run market research and business "
                         "cases, and present recommendations to C-suite stakeholders."),
    ),
    IndustryFixture(
        slug="legal",
        industry="Legal Services",
        resume_file="05-legal.txt",
        expected_occupation="Attorney / Legal Counsel",
        discipline="legal",
        own_title="Corporate Associate Attorney",
        company="Skadden, Arps",
        company_titles=("Associate Attorney", "Corporate Counsel"),
        company_snippet=("Draft and negotiate commercial contracts, lead M&A legal due "
                         "diligence, and advise clients on regulatory compliance."),
        job_title="Corporate Associate Attorney, M&A",
        job_description=("Draft and negotiate purchase agreements and commercial contracts, "
                         "lead legal due diligence, and advise on corporate governance, "
                         "securities, and regulatory compliance. JD and NY bar admission required."),
    ),
    IndustryFixture(
        slug="real-estate",
        industry="Real Estate",
        resume_file="06-real-estate.txt",
        expected_occupation="Real Estate",
        discipline="finance",
        own_title="Real Estate Acquisitions Analyst",
        company="Tishman Speyer",
        company_titles=("Acquisitions Analyst", "Asset Manager"),
        company_snippet=("Underwrite commercial real estate acquisitions; build ARGUS pro "
                         "forma models and cap-rate analyses across office and multifamily."),
        job_title="Acquisitions Analyst, Commercial Real Estate",
        job_description=("Underwrite commercial real estate acquisitions, building pro forma "
                         "cash-flow and cap-rate models in ARGUS, performing due diligence on "
                         "leases and rent rolls, and supporting asset management."),
    ),
    IndustryFixture(
        slug="media-publishing",
        industry="Media & Publishing",
        resume_file="07-media-publishing.txt",
        expected_occupation="Editorial / Content",
        discipline="marketing",
        own_title="Managing Editor",
        company="Condé Nast",
        company_titles=("Managing Editor", "Content Strategist"),
        company_snippet=("Lead editorial teams and content strategy; edit features, manage "
                         "the CMS workflow, and grow audience engagement under AP style."),
        job_title="Managing Editor, Digital",
        job_description=("Own the editorial calendar and content strategy for a digital "
                         "publication: assign and copy edit features, manage the CMS publishing "
                         "workflow, uphold AP style, and grow audience engagement."),
    ),
    IndustryFixture(
        slug="advertising-marketing",
        industry="Advertising & Marketing",
        resume_file="08-advertising-marketing.txt",
        expected_occupation="Marketing Manager",
        discipline="marketing",
        own_title="Marketing Manager, Growth",
        company="Ogilvy",
        company_titles=("Marketing Manager", "Growth Marketing Manager"),
        company_snippet=("Drive demand generation and brand campaigns across SEO, SEM, and "
                         "paid social; own marketing analytics on CAC, LTV, and funnel."),
        job_title="Growth Marketing Manager",
        job_description=("Own demand generation and growth marketing across SEO, SEM, paid "
                         "social, and lifecycle email. Lead brand campaigns and go-to-market "
                         "launches and track CAC, LTV, and funnel conversion."),
    ),
    IndustryFixture(
        slug="retail-fashion",
        industry="Retail & Fashion",
        resume_file="09-retail-fashion.txt",
        expected_occupation="Retail / Merchandising",
        discipline="operations",
        own_title="Senior Retail Buyer",
        company="Macy's",
        company_titles=("Retail Buyer", "Merchandising Manager"),
        company_snippet=("Build seasonal assortment plans and open-to-buy; negotiate with "
                         "vendors and drive sell-through and margin through markdown strategy."),
        job_title="Senior Buyer, Womenswear",
        job_description=("Manage a multi-million dollar buying budget: build seasonal "
                         "assortment plans and open-to-buy, negotiate vendor terms, and drive "
                         "sell-through and margin through allocation and markdown strategy."),
    ),
    IndustryFixture(
        slug="hospitality-tourism",
        industry="Hospitality & Tourism",
        resume_file="10-hospitality-tourism.txt",
        expected_occupation="Hospitality Management",
        discipline="operations",
        own_title="Hotel Operations Manager",
        company="Marriott International",
        company_titles=("Hotel Operations Manager", "Front Office Manager"),
        company_snippet=("Oversee front office, housekeeping, and food and beverage; drive "
                         "guest satisfaction, occupancy, and revenue management on Opera PMS."),
        job_title="Hotel Operations Manager",
        job_description=("Oversee front office, housekeeping, and food and beverage operations "
                         "for a full-service hotel. Drive guest satisfaction and occupancy, "
                         "manage reservations and banquets, and partner on revenue management."),
    ),
    IndustryFixture(
        slug="education",
        industry="Education",
        resume_file="11-education.txt",
        expected_occupation="Education / Teaching",
        discipline="education",
        own_title="High School Teacher",
        company="NYC Public Schools",
        company_titles=("High School Teacher", "Instructional Coordinator"),
        company_snippet=("Teach and design curriculum aligned to state standards; use "
                         "differentiated instruction and assessment to raise student outcomes."),
        job_title="High School Mathematics Teacher",
        job_description=("Teach mathematics and design curriculum aligned to state standards. "
                         "Use differentiated instruction, lesson planning, and formative "
                         "assessment, and develop IEP accommodations for diverse learners."),
    ),
    IndustryFixture(
        slug="insurance",
        industry="Insurance",
        resume_file="12-insurance.txt",
        expected_occupation="Insurance / Underwriting",
        discipline="finance",
        own_title="Commercial Lines Underwriter",
        company="AIG",
        company_titles=("Commercial Underwriter", "Actuarial Analyst"),
        company_snippet=("Underwrite property and casualty risk for commercial accounts; "
                         "evaluate exposures and loss history and price to loss-ratio targets."),
        job_title="Commercial Lines Underwriter",
        job_description=("Underwrite property and casualty risk for middle-market commercial "
                         "accounts: evaluate exposures and loss history, structure policies, set "
                         "premiums to meet loss-ratio targets, and negotiate renewals with brokers."),
    ),
    IndustryFixture(
        slug="accounting",
        industry="Accounting",
        resume_file="13-accounting.txt",
        expected_occupation="Accountant / Auditor",
        discipline="finance",
        own_title="Senior Accountant",
        company="Deloitte",
        company_titles=("Senior Accountant", "Audit Associate"),
        company_snippet=("Own the month-end close, general ledger, and GAAP financial "
                         "statements; coordinate the external audit and SOX controls testing."),
        job_title="Senior Accountant",
        job_description=("Own the month-end and year-end close: prepare journal entries, "
                         "account reconciliations, and GAAP financial statements; manage AP/AR "
                         "and the general ledger; and coordinate the annual audit and SOX testing."),
    ),
    IndustryFixture(
        slug="biotech-pharma",
        industry="Biotech & Life Sciences",
        resume_file="14-biotech-pharma.txt",
        expected_occupation="Clinical Research / Life Sciences",
        discipline="healthcare",
        own_title="Clinical Research Associate",
        company="Pfizer",
        company_titles=("Clinical Research Associate", "Regulatory Affairs Specialist"),
        company_snippet=("Monitor oncology clinical trials for GCP compliance; prepare "
                         "regulatory submissions and manage clinical data and trial master files."),
        job_title="Clinical Research Associate, Oncology",
        job_description=("Monitor Phase II-III oncology clinical trials: conduct source-data "
                         "verification, ensure protocol and Good Clinical Practice (GCP) "
                         "compliance, prepare FDA and IRB regulatory submissions, and track "
                         "adverse events and pharmacovigilance."),
    ),
    IndustryFixture(
        slug="architecture-construction",
        industry="Architecture & Construction",
        resume_file="15-architecture-construction.txt",
        expected_occupation="Architecture / Construction",
        discipline="design",
        own_title="Project Architect",
        company="Skidmore, Owings & Merrill",
        company_titles=("Project Architect", "Design Architect"),
        company_snippet=("Lead design development and construction documents in Revit; "
                         "coordinate consultants and navigate NYC building codes and permitting."),
        job_title="Project Architect, Commercial",
        job_description=("Lead design development and construction documents for commercial "
                         "projects in Revit and AutoCAD. Coordinate structural and MEP "
                         "consultants, manage BIM models, and navigate building codes, zoning, "
                         "and permitting through construction administration."),
    ),
    IndustryFixture(
        slug="transportation-logistics",
        industry="Transportation & Logistics",
        resume_file="16-transportation-logistics.txt",
        expected_occupation="Supply Chain / Logistics",
        discipline="operations",
        own_title="Supply Chain Analyst",
        company="UPS",
        company_titles=("Supply Chain Analyst", "Logistics Manager"),
        company_snippet=("Own demand planning and forecasting; optimize logistics, freight, "
                         "and warehouse throughput in SAP across distribution centers."),
        job_title="Supply Chain Analyst",
        job_description=("Own demand planning and forecasting across thousands of SKUs, "
                         "reducing stockouts and excess inventory. Analyze logistics and "
                         "distribution in SAP, optimize freight and warehouse throughput, and "
                         "partner with procurement on sourcing and purchase orders."),
    ),
    IndustryFixture(
        slug="nonprofit",
        industry="Nonprofit & Social Services",
        resume_file="17-nonprofit.txt",
        expected_occupation="Nonprofit / Social Services",
        discipline="operations",
        own_title="Director of Development",
        company="Robin Hood Foundation",
        company_titles=("Development Manager", "Program Director"),
        company_snippet=("Lead fundraising and grant writing; manage community programs, "
                         "volunteers, and donor relationships and report impact to funders."),
        job_title="Director of Development & Programs",
        job_description=("Lead fundraising and development: cultivate major donors, write and "
                         "steward foundation and government grants, and manage community "
                         "programs, volunteers, and outreach. Report impact metrics to the board."),
    ),
    IndustryFixture(
        slug="government",
        industry="Government & Public Policy",
        resume_file="18-government.txt",
        expected_occupation="Public Policy / Government",
        discipline="consulting",
        own_title="Policy Analyst",
        company="City of New York",
        company_titles=("Policy Analyst", "Program Analyst"),
        company_snippet=("Conduct policy analysis and program evaluation on housing and "
                         "transportation; draft policy briefs and brief senior officials."),
        job_title="Policy Analyst, Housing",
        job_description=("Conduct policy analysis and program evaluation on housing "
                         "initiatives, model budget and constituent impact, draft policy briefs "
                         "and testimony, and brief senior officials on regulatory and "
                         "intergovernmental matters."),
    ),
    IndustryFixture(
        slug="data-analytics",
        industry="Data & Analytics",
        resume_file="19-data-analytics.txt",
        expected_occupation="Data Analyst",
        discipline="data",
        own_title="Senior Data Analyst",
        company="Spotify",
        company_titles=("Data Analyst", "Business Intelligence Analyst"),
        company_snippet=("Build dashboards and reporting in Tableau and Looker; write SQL to "
                         "model warehouse data and define KPIs for product and business teams."),
        job_title="Senior Data Analyst, Business Intelligence",
        job_description=("Build executive dashboards in Tableau and Looker and write complex "
                         "SQL to model warehouse data and define KPIs. Deliver self-serve "
                         "reporting and partner on A/B test readouts and business intelligence."),
    ),
    IndustryFixture(
        slug="human-resources",
        industry="Human Resources",
        resume_file="20-human-resources.txt",
        expected_occupation="Recruiter / People",
        discipline="hr",
        own_title="Senior Technical Recruiter",
        company="Bloomberg",
        company_titles=("Technical Recruiter", "Talent Acquisition Partner"),
        company_snippet=("Own full-cycle recruiting and sourcing for engineering roles; "
                         "partner with hiring managers and manage the ATS and candidate experience."),
        job_title="Senior Technical Recruiter",
        job_description=("Own full-cycle recruiting for engineering and product roles: source "
                         "candidates, run interviews, and close offers. Partner with hiring "
                         "managers on workforce planning and candidate experience and manage "
                         "the ATS and recruiting analytics."),
    ),
)

# Sanity: 20 industries, unique slugs, unique expected occupations, files present.
assert len(FIXTURES) == 20
assert len({f.slug for f in FIXTURES}) == 20
assert len({f.expected_occupation for f in FIXTURES}) == 20
