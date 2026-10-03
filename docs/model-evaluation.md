# Model evaluation and governance

## Two distinct records

**Prospective ledger:** actual forecasts frozen at issue time, with later outcomes appended. Initially it has issued predictions and zero resolved outcomes. This is not a broken results screen; the future has not happened.

**Retrospective replay:** walk-forward experiments reconstruct what a method would have produced on prefixes of an already available history. These do not populate the prospective ledger. Backfilled provider history can be revised and is not necessarily a point-in-time archive.

## Validation rules

- No random time-series train/test splits.
- Expanding-window and optional rolling-window splits purge training labels through their horizon; the last training label must end strictly before validation starts.
- Baseline analogue outcomes finish before the current query window; chosen analogue intervals do not overlap each other.
- Walk-forward test origins are spaced by the horizon, avoiding overlapping target intervals.
- Preprocessing in logistic regression fits inside each training fold.
- Future label columns are never present in the feature matrix.
- Appending extreme future values must not change an already computed feature prefix; tests enforce this for all smoothers and ML features.

## Metrics

The implementation reports accuracy, balanced accuracy, macro precision/recall/F1, MCC, multiclass Brier score, log loss and one-vs-rest reliability bins with sample counts. Brier is the **sum** of three squared errors, averaged over observations: range 0–2; uniform three-class prediction gives 2/3. Do not compare it with a differently normalized binary Brier score.

Prospective results include breakdowns by horizon, confidence and available asset-level regime. Small or one-class samples can give unstable metrics. No statistically powered superiority or future profitability is inferred from a single favorable replay. ROC-AUC, return-conditioned performance and strategy P&L are not enabled in v0.1; there is no hypothetical investment-return chart to confuse with actual returns.

## Research ensemble

`trendforge evaluate ENTITY --horizon 7 --ensemble` trains logistic regression, random forest and histogram gradient boosting inside purged chronological folds. It compares their probabilities and an equal-weight ensemble. Inputs are return_1, return_7, volatility_20, SMA gap and relative acceleration. Trees have restricted depth/leaf sizes. The models remain offline research results and never replace the baseline just because they look better on the inspected sample.

Platt and isotonic utilities require a separate later calibration holdout, at least 100 samples and at least 10 of every class. They reject overlap with base-model training labels. Using the utilities is not itself proof of calibration; a further evaluation holdout is required. No calibration fit is fabricated for synthetic dashboard forecasts.

## Promotion gate

`promotion_decision` rejects candidates unless they have at least 200 matured **prospective real-data** holdout predictions, the same locked evaluation ID as production, at least 0.01 Brier improvement, no log-loss or balanced-accuracy regression, and passed regime/calibration checks. Even an eligible result requires review; automatic promotion is false. No candidate record overwrites the previous model card.

This is infrastructure, not a completed live model-governance operation. In particular, input drift/accuracy-degradation dashboards, paired bootstrap tests, provider revision archives, delisted-stock universes and tuning-budget tracking remain roadmap work. OOD checks at forecast time do not substitute for continuous model drift monitoring.

## Reproducibility

Keep the input snapshot, engine configuration, immutable forecast, model implementation and dependency locks together. The audit exports include potentially licensed data: do not publish real-provider snapshots without permission. Demo snapshots are safe synthetic examples. `trendforge verify-audit` checks the feature hash and exact baseline probabilities against the stored inputs.
