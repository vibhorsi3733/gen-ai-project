"""Skill extraction with a curated dictionary (canonical name -> aliases).

Why a dictionary and not the LLM: "top asked skills" needs *canonical* names to count
("ReactJS", "React.js", "React" must be one bar). A fixed list is deterministic,
free, works without an API key, and re-runs over the whole archive cost nothing.
Ambiguous short names (C, R, Go) are matched only in unambiguous forms.
"""
import re

# category -> {canonical skill: [regex alternatives, matched case-insensitively on word boundaries]}
SKILLS: dict[str, dict[str, list[str]]] = {
    "Programming": {
        "Python": [r"python"],
        "Java": [r"java(?!\s*script)"],
        "JavaScript": [r"javascript", r"\bjs\b", r"es6"],
        "TypeScript": [r"typescript"],
        "C++": [r"c\+\+", r"cpp"],
        "C#": [r"c#", r"\.net", r"dotnet"],
        "Go": [r"golang", r"\bgo\s*\(lang\)"],
        "Kotlin": [r"kotlin"],
        "Swift": [r"swift(?!ly)"],
        "Scala": [r"scala"],
        "Rust": [r"\brust\b(?!ic)"],
        "PHP": [r"php"],
        "Ruby": [r"ruby", r"rails"],
        "Bash / Shell": [r"bash", r"shell script\w*", r"unix shell"],
        "DSA": [r"data structures", r"\bdsa\b", r"algorithms? (?:and|&) data structures?", r"(?:design|analysis) of algorithms",
                r"algorithmic problem[- ]solving"],   # bare "algorithm" matched mission statements
        "OOP": [r"object[- ]oriented", r"\boops?\b"],
    },
    "Web & mobile": {
        "React": [r"react(?:\.?js)?(?! native)"],
        "React Native": [r"react native"],
        "Angular": [r"angular(?:js)?"],
        "Vue": [r"vue(?:\.?js)?"],
        "Node.js": [r"node(?:\.?js)?\b"],
        "Next.js": [r"next\.?js"],
        "HTML / CSS": [r"html5?", r"css3?"],
        "Spring Boot": [r"spring\s*(?:boot|framework|mvc)"],
        "Django": [r"django"],
        "Flask / FastAPI": [r"flask", r"fastapi"],
        "REST APIs": [r"rest(?:ful)?\s*(?:apis?|services|web services)", r"restful"],
        "GraphQL": [r"graphql"],
        "Android": [r"android"],
        "iOS": [r"\bios\b"],
        "Flutter": [r"flutter"],
        "Microservices": [r"micro-?services?"],
    },
    "Data & AI": {
        "SQL": [r"\bsql\b", r"t-sql", r"pl/sql"],
        "Excel": [r"excel", r"spreadsheets?", r"google sheets", r"vlookup", r"pivot tables?"],
        "Power BI": [r"power\s*bi"],
        "Tableau": [r"tableau"],
        "Statistics": [r"statistic(?:s|al)"],
        "Machine Learning": [r"machine learning", r"\bml\b"],
        "Deep Learning": [r"deep learning", r"neural networks?"],
        "Generative AI / LLMs": [r"generative ai", r"gen\s*ai", r"\bllms?\b", r"large language models?", r"prompt engineering",
                                 r"\brag\b"],
        "NLP": [r"\bnlp\b", r"natural language processing"],
        "Computer Vision": [r"computer vision", r"opencv"],
        "PyTorch / TensorFlow": [r"pytorch", r"tensorflow", r"keras"],
        "Pandas / NumPy": [r"pandas", r"numpy", r"scikit-?learn", r"sklearn"],
        "Spark": [r"\bspark\b", r"pyspark"],
        "ETL / Data pipelines": [r"\betl\b", r"elt\b", r"data pipelines?", r"airflow", r"dbt\b"],
        "Data analysis": [r"data analysis", r"data analytics", r"analy[sz]e data"],
    },
    "Cloud & DevOps": {
        "AWS": [r"\baws\b", r"amazon web services"],
        "Azure": [r"azure"],
        "GCP": [r"\bgcp\b", r"google cloud"],
        "Docker": [r"docker", r"containeri[sz]\w+"],
        "Kubernetes": [r"kubernetes", r"\bk8s\b"],
        "Linux": [r"linux", r"unix"],
        "CI/CD": [r"ci\s*/\s*cd", r"jenkins", r"github actions", r"gitlab ci"],
        "Git": [r"\bgit\b", r"github", r"version control"],
        "Terraform": [r"terraform", r"infrastructure as code"],
        "Networking": [r"networking", r"tcp/ip", r"\bdns\b"],
        "Cybersecurity": [r"cyber\s*security", r"information security", r"\bsiem\b", r"vulnerabilit\w+"],
        "Testing / QA": [r"selenium", r"test automation", r"unit test\w*", r"\bqa\b", r"quality assurance", r"cypress",
                         r"playwright"],
    },
    "Databases": {
        "PostgreSQL": [r"postgres(?:ql)?"],
        "MySQL": [r"mysql"],
        "MongoDB": [r"mongo(?:db)?"],
        "Redis": [r"redis"],
        "Kafka": [r"kafka"],
        "NoSQL": [r"nosql"],
        "Snowflake / BigQuery": [r"snowflake", r"bigquery", r"redshift", r"databricks"],
    },
    "Business tools": {
        "CRM (Salesforce etc.)": [r"\bcrm\b", r"salesforce", r"hubspot", r"zoho"],
        "SAP / ERP": [r"\bsap\b", r"\berp\b", r"oracle (?:erp|financials|fusion)"],
        "MS Office": [r"ms office", r"microsoft office", r"powerpoint", r"\bms word\b"],
        "Jira": [r"jira", r"confluence"],
        "Figma": [r"figma", r"adobe xd", r"sketch app"],
        "Adobe Creative Suite": [r"photoshop", r"illustrator", r"premiere pro", r"after effects", r"adobe creative"],
        "Google Analytics": [r"google analytics", r"\bga4\b"],
        "SEO / SEM": [r"\bseo\b", r"\bsem\b", r"search engine optimi[sz]ation", r"google ads"],
        "Accounting (Tally / GST)": [r"tally", r"\bgst\b", r"accounting", r"bookkeeping", r"reconciliation"],
    },
    "Professional skills": {
        "Communication": [r"communication skills?", r"(?:verbal|written) communication", r"communicat\w+ effectively",
                          r"excellent communication"],
        "English proficiency": [r"fluen\w+ in english", r"english (?:fluency|proficiency)", r"good english"],
        "Hindi / regional language": [r"\bhindi\b", r"kannada", r"tamil", r"telugu", r"marathi", r"bengali",
                                      r"regional language"],
        "Problem solving": [r"problem[- ]solving", r"analytical skills?", r"critical thinking"],
        "Teamwork": [r"team player", r"team-?work", r"work(?:ing)? (?:well )?in (?:a|cross-functional) teams?", r"collaborative (?:mindset|attitude|spirit)"],
        "Stakeholder management": [r"stakeholder"],
        "Negotiation": [r"negotiat\w+"],
        "Presentation": [r"presentation skills?", r"present\w* to (?:clients|stakeholders|leadership)"],
        "Customer handling": [r"customer[- ](?:handling|service|facing|interaction)", r"client[- ]facing"],
        "Project management": [r"project management", r"\bagile\b", r"scrum"],
    },
}

SKILL_CATEGORY = {s: cat for cat, d in SKILLS.items() for s in d}
_COMPILED = [(s, re.compile(r"(?<![\w+#])(?:" + "|".join(alts) + r")(?![\w+#])", re.I))
             for d in SKILLS.values() for s, alts in d.items()]


ALL_SKILLS = list(SKILL_CATEGORY)

# Sentences that describe the COMPANY, its products, benefits or legal text, not the job.
# Bug this fixes: every MongoDB post opens with "MongoDB Atlas ... is available across AWS, Google
# Cloud, and Microsoft Azure", so recruiters were tagged AWS / Azure / GCP.
_BOILER = re.compile(
    r"(about (?:us|the company|the team)\b|who we are|our (?:mission|platform|products?|customers|clients|"
    r"offices|culture|values|story)|customers? (?:worldwide|include|around)|\bover \d[\d,]* (?:customers|employees)|"
    r"offices (?:worldwide|in|across)|founded in|headquartered|fortune \d+|backed by|leading (?:provider|platform)|"
    r"equal (?:employment )?opportunity|we (?:are an?|celebrate|value) (?:equal|diverse|inclusive)|"
    r"benefits|perks|insurance|paid (?:time off|leave)|parental leave|wellness|stock options|esops?|"
    r"reasonable accommodation|privacy (?:policy|notice)|background (?:check|verification)|recruitment fraud|"
    r"do not (?:ask|charge)|never (?:ask|charge)s? .* (?:fee|money)|is (?:an? )?(?:global|leading|world)|"
    r"(?:platform|product) is available)", re.I)


def jd_sentences(description: str, company: str = "") -> list[str]:
    """The job description split into sentences, with company/benefit/legal boilerplate removed.
    A sentence that names the company and describes it ("MongoDB is…", "At Bosch we…") is dropped too."""
    text = " ".join((description or "").split())
    sents = [s.strip() for s in re.split(r"(?<=[.!?•])\s+|\s+[•·▪●]\s+|\s-\s(?=[A-Z])", text) if len(s.strip()) > 3]
    co = re.escape(company.strip().split()[0]) if company.strip() else None
    out = []
    for s in sents:
        if len(s) > 500:   # a long block (e.g. a flattened list) is never dropped whole
            out.append(s)
            continue
        if _BOILER.search(s):
            continue
        if co and re.search(rf"\b{co}\b", s, re.I) and re.search(
                r"\b(is|are|was|has|have|offers?|provides?|builds?|helps?|serves?|powers?|runs?|leads?)\b", s, re.I) \
                and not re.search(r"\b(you|your|candidate|role|will)\b", s, re.I):
            continue
        out.append(s)
    return out


def skill_evidence(title: str, description: str, company: str = "") -> dict[str, str]:
    """{skill: the title or JD sentence that mentions it}, boilerplate excluded."""
    found = {}
    for s, rx in _COMPILED:
        if rx.search(title or ""):
            found[s] = f"[title] {title}"
    for sent in jd_sentences(description, company):
        for s, rx in _COMPILED:
            if s not in found and rx.search(sent):
                found[s] = sent[:240]
    return {s: found[s] for s in ALL_SKILLS if s in found}   # dictionary order


def mentioned_anywhere(title: str, description: str) -> set[str]:
    """Every dictionary skill that appears anywhere in the post (boilerplate included).
    Used only to ground LLM output: a technical skill the text never mentions is dropped."""
    text = f"{title}\n{description or ''}"
    return {s for s, rx in _COMPILED if rx.search(text)}


def extract_skills(title: str, description: str, company: str = "") -> list[str]:
    """Keyword fallback (no LLM): canonical skills in the title or the JD's non-boilerplate sentences.
    A skill that is the employer's own name (MongoDB at MongoDB, Databricks at Databricks) is skipped:
    every one of their posts mentions it, recruiters included. The LLM path can still keep it."""
    own = {s for s, rx in _COMPILED if company and rx.search(company)}
    return [s for s in skill_evidence(title, description, company) if s not in own]


def final_skills(llm_skills: list[str] | None, title: str, description: str, company: str = "") -> tuple[list[str], str]:
    """The skills shown on a job card, and where they came from. Used by the pipeline and the eval alike.
      * LLM answer, grounded: a technical skill the post never mentions is dropped (no invented skills).
      * LLM returned nothing although the JD scan found 2+ skills -> treated as an omission (the lite model
        did this on 5 of 50 posts: SQL missing for a BI Developer), so the scan's skills are used.
      * No LLM answer -> the JD scan (boilerplate already excluded)."""
    rules = extract_skills(title, description, company)
    if llm_skills is None:
        return rules, "rules"
    seen = mentioned_anywhere(title, description)
    kept = [s for s in llm_skills if s in seen or SKILL_CATEGORY.get(s) == "Professional skills"]
    if not kept and len(rules) >= 2:
        return rules, "rules (LLM returned none)"
    return kept, "llm"
