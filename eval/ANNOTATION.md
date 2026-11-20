# Annotation agreement (50 posts)

| Field | Agreement | Cohen's kappa |
|---|---|---|
| role | 49/50 (98%) | 0.98 |
| cities | 50/50 (100%) | 1.00 |
| level | 45/50 (90%) | 0.79 |
| skills (y/n per candidate) | 234/238 (98%) | |

## Method

The 50 posts were labelled by **two independent annotators**: separate Claude agents, each blind to the
tagger's predictions and to the other annotator, given the same written guideline (the taxonomy definitions
in `pipeline/tagger.py`). Where they agreed, that label is gold. The 6 field
disagreements were adjudicated by reading the job description; each decision and its reason is in
`eval/annotations/adjudication.json` and in the `notes` column of `eval/labels.csv`.

The tagger being evaluated is **Gemini** and the annotators are **Claude**, so the model is not grading itself.
These are AI annotations, not a human hand-check. A human can overwrite any row in `eval/labels.xlsx`
and re-run `eval.import_labels` + `eval.score`.

Skill judgements: 234 of 238 candidate skills got the same y/n from both annotators;
0 split decisions are left unmarked and excluded from the skills precision figure.
