# HW2 — Explainable Credit Approval

*15.C51 Project #2 (Spring 2026). Explainable ML on the UCI Credit Approval
dataset, with a loan-level P&L backtest.*

**Team:** Arturo Favara, Jacob Lebovitz, Ben Noymer, Powell Zhang.

## The assignment

> Using credit approval data from the UCI Machine Learning Repository,
> develop and backtest an ML model for credit scoring that yields some
> form of explainability for individual credit decisions.
>
> — *Project #2 handout, 15.C51 Spring 2026*

## Approach

The project trains four models with deliberately different
interpretability profiles, runs each through both **statistical** and
**economic** evaluation, and compares them on an apples-to-apples basis.

| Model | Interpretability layer | Why it's here |
|-------|------------------------|---------------|
| Decision Tree (depth=3) | Tree visualisation | Fully transparent baseline |
| Logistic Regression | Coefficients | Linear baseline, regulatory-friendly |
| Explainable Boosting Machine (`interpret`) | Per-feature shape functions + SHAP | Glass-box GAM, native interpretability |
| XGBoost (with class-imbalance weighting) | LIME (per-instance) | Black-box upper bound for accuracy |

A k-means clustering pre-processing step (k chosen by silhouette, with a
manual override of k=4) feeds an additional "decision tree explaining
clusters" view of the population.

## What's evaluated, beyond accuracy

The notebooks build a small loan-economics layer on top of the classifiers
to convert probability scores into dollar P&L:

- **Loan-level P&L engine** (`loan_pnl`) — sweeps decision thresholds, scores
  every test applicant, and computes interest income (good loan ⇒ margin),
  credit losses (bad loan ⇒ LGD × EAD), opportunity cost (rejected good
  loan), realised P&L, ROA, approval rate, and book bad rate.
- **Profit curve / threshold optimisation** — for each model, find τ\*
  that maximises realised P&L; shows the cost-asymmetry trade-off
  (`profit_curve(y_true, y_hat, r)` over `R = 2^[-2, …, 6]`).
- **Macro stress test** — sensitivity grid over LGD ∈ [0.30, 0.90] and
  interest margin ∈ [0.02, 0.15]; per-cell re-optimisation of τ\*; "stress
  wins" counts how often each model leads.
- **Bootstrap confidence intervals** — N=500 resamples of the test set
  (preserving paired exposures), distribution of optimal P&L per model.
- **ROC / AUC, precision-recall, calibration, Brier score** — the standard
  statistical evaluation in parallel.

Headline output is a single comparison frame: AUC, optimal τ, P&L at τ\*,
ROA, approval rate, book bad rate, stress wins, bootstrap median.

## Files

```
HW2/
├── p2.ipynb                    # primary notebook — EDA → models → P&L → stress
├── p2_report_matching.ipynb    # variant aligned with the written report
└── README.md
```

The two notebooks are identical except for cell 34, where the
`*_report_matching` version uses the **raw (pre-scaling)** A15 income
column to derive Exposure-At-Default in dollar units, so portfolio
exposure and dollar P&L numbers match the figures in the written report.
The primary notebook uses a min-shifted version of the standardised A15
as a positive proxy.

## Data

UCI Credit Approval (`fetch_ucirepo(id=27)`) — 690 rows, 15 anonymised
features (`A1–A15`), binary target `A16 ∈ {+, -}`. The notebook documents
the conventional best-guess column mapping (cross-referenced with Statlog
Australian Credit Approval) and flags the protected-attribute columns
(A1 gender, A4 marital status, A7 ethnicity) that would warrant fairness
analysis in a real deployment. Rows with any missing values are dropped;
categoricals are one-hot encoded with `drop_first=True`; high-correlation
features (|ρ| > 0.95) are pruned; continuous features are standardised
on the training fold only.

## Reproducing the notebooks

```bash
pip install ucimlrepo interpret shap xgboost lime
jupyter notebook p2.ipynb
```

Plots are written next to the notebook (`plot1_roc.png`,
`plot2_feature_importance.png`, `plot3a_lime_approved.png`,
`plot3b_lime_denied.png`, `plot4_lime_stability.png`,
`roc_comparison.png`).

## Grading axes (from the project handout)

- Completeness of the financial analysis (25 pts)
- Novelty (25 pts)
- Readability (25 pts)
- Source attribution, including all LLMs and prompts (25 pts)

The notebooks aim at the financial-analysis axis through the loan-level
P&L engine + stress grid + bootstrap CIs (rather than stopping at AUC
plots), and at the explainability axis by stacking per-instance LIME, a
glass-box GAM, classical coefficients, and a tree visualisation in the
same comparison.
