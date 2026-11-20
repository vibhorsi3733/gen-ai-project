# Tagging accuracy on 50 labelled posts

Gold labels: see eval/ANNOTATION.md (2 independent annotators + adjudication).

Accuracy with Wilson 95% confidence interval. `cities` must match the gold set exactly.

| Arm | Role | Cities | Role + cities | Level | Cost / 1,000 posts |
|---|---|---|---|---|---|
| baseline | 64% [50-76] | 92% [81-97] | 60% [46-72] | n/a | free |
| gemini-3.5-flash-lite | 80% [67-89] | 98% [90-100] | 78% [65-87] | 74% [60-84] | $0.332 (in 410 / out 84 tok per post) |

## Paired comparison on role (posts where exactly one arm is right)

- gemini-3.5-flash-lite right & baseline wrong: **13**; baseline right & gemini-3.5-flash-lite wrong: **5**

## Disagreements: gemini-3.5-flash-lite

| Title | Location | Gold | Predicted |
|---|---|---|---|
| Growth Associate | Raipur, CG, India | level: Early career | Experienced |
| business development & strategic partnerships - d2c | bengaluru | level: Experienced | Early career |
| Product Research Specialist (W from Groww) | Bengaluru-VTP, India | role: Finance / Accounting | Product Management |
| Product Research Specialist (W from Groww) | Bengaluru-VTP, India | level: Early career | Experienced |
| SDE II - Data Engineer | Lucknow | role: Data / Analytics / ML | Software Engineering |
| SDE II - Data Engineer | Lucknow | level: Experienced | Early career |
| MIS Executive - Arctic Engine | Bengaluru, Karnataka, India | role: Data / Analytics / ML | Operations / Supply Chain |
| Coordinator, Marketing Operations | Bangalore, India | role: Marketing | Operations / Supply Chain |
| Recruiter, R&D | Remote, Canada; Remote, India; Remote, P | level: Experienced | Early career |
| Personal Assistant | Mumbai | role: Other | Operations / Supply Chain |
| Data Engineer (SDE 2) | Bengaluru | role: Data / Analytics / ML | Software Engineering |
| Full Stack Software Development Engineer II | Bengaluru, Karnataka, India | level: Experienced | Early career |
| Associate of R&D Strategic Finance (FP&A) | Chennai | level: Experienced | Early career |
| CSR Associate - Impact, Monitoring & Evaluation | bengaluru, India | role: Data / Analytics / ML | Other |
| Cartographer | Vadodara, GJ, India | cities: Other India | Other India; India (unspecified) |
| Payroll Accountant | Bengaluru, India | level: Early career | Experienced |
| Deployment Strategist | India | role: Product Management | Consulting / Strategy |
| Deal Desk Strategist  | Chennai, India | role: Sales / Business Development | Operations / Supply Chain |
| Executive - Video Editor | Mumbai, MH, India | level: Early career | Experienced |
| business development & partnerships | bengaluru | level: Experienced | Early career |
| Programmatic Trading Specialist, APAC | Gurugram, IN | role: Marketing | Sales / Business Development |
| Intermediate Backend Engineer, India | Bangalore, India | level: Experienced | Early career |
| Analyst II - SIEM/SecOps | Hyderabad | level: Experienced | Early career |
| Product Support Operations Associate, Weekend Shift | Bengaluru | level: Fresher | Early career |
