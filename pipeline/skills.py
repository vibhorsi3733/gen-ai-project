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
        "DSA": [r"data structures?", r"algorithms?", r"\bdsa\b"],
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


def extract_skills(title: str, description: str) -> list[str]:
    """Canonical skills mentioned in the title or description, in dictionary order."""
    text = f"{title}\n{description or ''}"
    return [s for s, rx in _COMPILED if rx.search(text)]
