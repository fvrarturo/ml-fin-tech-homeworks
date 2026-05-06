# 15.C51 — Modeling with Machine Learning: Financial Technology

Course projects for **15.C51 (Spring 2026)** at MIT Sloan, taught by Andrew W. Lo
and Paul F. Mende. The course explores ML techniques applied to modern finance:
valuation, credit, proprietary trading, portfolio management, market structure,
risk management, and NLP.

This repository collects the two team projects assigned in the course.

## Repository layout

```
ml-fin-tech-homeworks/
├── HW1/   Project #1 — Proprietary Trading on the Dow Jones 30
└── HW2/   Project #2 — Credit Approval with Explainable ML
```

Each subdirectory has its own `README.md` with the project specification, the
methodology, the deliverables, and pointers to the code.

## Project #1 — Proprietary Trading (DJ30, 2016–2025)

A horizon-comparison study of mean-reversion and momentum on the Dow Jones 30,
spanning **six time scales** from 30 minutes (TAQ) to 6 months (CRSP). Twelve
backtests run under a uniform tercile long-short methodology, with a full
robustness suite (cost sensitivity, bid-ask-bounce diagnostics, regime
splits, factor exposures, look-ahead audits) feeding into an Investment
Committee Memorandum.

Headline finding: the only horizon that survives a Bonferroni-corrected
significance test on net Sharpe is the H2 intraday reversal (first-30 min →
rest-of-day), at net Sharpe ≈ 2.5 with ~1.5 bps per-side execution cost.

See [HW1/README.md](HW1/README.md) for the full write-up.

## Project #2 — Credit Approval with Explainable ML

An explainable credit-scoring pipeline on the **UCI Credit Approval** dataset,
comparing four models (Decision Tree, Logistic Regression, Explainable Boosting
Machine, XGBoost) with corresponding interpretability layers (tree visualisation,
coefficients, SHAP, LIME). The evaluation goes beyond AUC: a loan-level P&L
engine, an LGD × interest-margin stress grid, and bootstrap confidence
intervals on optimal P&L.

See [HW2/README.md](HW2/README.md) for the full write-up.

## Course context

- **Course:** [15.C51 — Modeling with Machine Learning: Financial Technology](https://canvas.mit.edu/courses/37562)
- **Instructors:** Andrew W. Lo, Paul F. Mende
- **TA:** Chaoyi Zhao
- **Term:** Spring 2026 (Apr 1 – May 6)
- **AI use policy:** LLMs are allowed with full attribution. See
  the per-project `llm_logs/` directories for prompts, models, and decision
  trails.

The course handouts (`Project1.pdf`, `Project2.pdf`, syllabus) are reproduced
in the per-project directories where they apply.
