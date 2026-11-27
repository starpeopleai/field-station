# Model decline audit and tuning — 17 November 2026

The newest evaluation added 2,642 reviewed images from one recording group: 97 anomalous and 2,545 non-anomalous. Stable falsely flagged 693 of those negatives. On the 110,047 unchanged images shared with the preceding run, Stable changed from 852 to 923 false positives and 1,174 to 1,178 true positives. Experimental improved slightly; Hybrid and Machine-only gave identical confusion counts on that shared cohort. Much of the apparent decline was the addition of a difficult recording, rather than all three learned classifiers deteriorating.

## Human recipe change

`human_nonlinear_v2` keeps the frozen MobileNetV3 Small RGB feature extractor and whole-review-box input contract. The learned classifier expands from 64 to 128 hidden units, trains for 60 rather than 40 epochs, and assigns 25% rather than 50% of total loss weight to anomalous examples. Recording balancing and duplicate-pixel weighting remain. Conflicting exact-pixel labels are excluded from fitting without modifying or deleting their source evidence.

Six recipes were compared across five recording-group folds. Each rotation used three folds for fitting, one for threshold selection, and one for evaluation. Threshold selection retained the baseline recipe's calibration recall. Pixels shared across folds were excluded. The selected recipe was repeated with a second seed.

| Seed | Recipe | False positives | True positives | Recall | Precision |
|---|---|---:|---:|---:|---:|
| 731 | Previous recipe | 1,635 | 995 | 76.25% | 37.83% |
| 731 | Revised recipe | 1,187 | 1,000 | 76.63% | 45.72% |
| 947 | Previous recipe | 1,565 | 990 | 75.86% | 38.75% |
| 947 | Revised recipe | 1,500 | 1,022 | 78.31% | 40.52% |

These are historical cross-validation results used for recipe development, not a frozen external test. Seed 947 corroborates the direction but shows meaningful variation. Do not substitute training accuracy for deployment generalization.

The final fit preserves all 115,336 human examples in its dataset manifest; four conflicting examples are excluded from fitting. The final operating thresholds are 0.43 for Stable and 0.60 for Experimental. An additional fixed-operating-point check superseded the initial 0.60/0.70 release settings: those settings improved training replay but reduced out-of-fold recall. On the same 112,689 images scored in the preceding evaluation:

| Profile | Previous TP / FP | Revised TP / FP |
|---|---:|---:|
| Stable | 1,275 / 1,616 | 1,297 / 942 |
| Experimental | 1,256 / 1,093 | 1,282 / 567 |

This last table is training-set replay. The final operating points were selected using historical out-of-fold development results, not an untouched prospective test; they are not calibrated probabilities. At the fixed deployed settings, the recording-disjoint comparisons were:

| Seed | Previous Stable TP / FP (0.78) | Revised Stable TP / FP (0.43) | Previous Experimental TP / FP (0.85) | Revised Experimental TP / FP (0.60) |
|---|---:|---:|---:|---:|
| 731 | 999 / 1,734 | 999 / 1,675 | 959 / 1,331 | 971 / 1,300 |
| 947 | 989 / 1,595 | 996 / 1,593 | 963 / 1,160 | 964 / 1,157 |

These generalization gains are modest and should not be confused with the much larger in-sample improvements. The CoreML export passed 512 checks spanning image order and score quantiles, with maximum probability drift below 0.000001. The field runtime also requires sustained healthy advancing recognition before release.

## Evaluation and automatic tuning repairs

- Evaluation now canonicalizes legacy labels exactly as training does. For example, `cloud` and `star` are non-anomalous; retired landscape labels and changed pixels still fail eligibility checks. Previously, 2,647 valid legacy examples were excluded as changed labels.
- A context revision prevents resuming stale eligibility results after this correction.
- Stable and Experimental reuse native inference only when weights and effective color policy match; their thresholds and confusion counts remain independent. Subsequent runs may reuse probabilities for identical pixels and inference policy, but always recheck current review eligibility.
- Hybrid tuning now reads verified current-model benchmark predictions and excludes its fitted recording groups and pixels. Its old pre-review prediction path yielded zero eligible rows after model changes, despite having 27,444 reserved reviewed examples available.
- Automatic tuning replays the whole-review-box classification contract. It no longer invents a minimum-size/context veto absent from that classifier, and it cannot improve false positives by reducing recall.

## Hybrid and Machine-only

Hybrid's nonlinear candidate improved calibration but failed the independent recording validation's recall guard. It was not promoted. Its restored tuner now has usable reserved data and measures actual tradeoffs instead of indefinitely reporting zero examples.

Machine-only currently trains on 1,159 machine-labeled examples, only 13 positive. Its preserved corpus has 14 positives. That is not comparable coverage to the human dataset. No human labels were inserted into this lane, and no threshold change was claimed to repair its lack of positive evidence.

## Evidence and reproducibility

Compact counts and native export checks are in `evidence/model-tuning-20261117.json`. Complete input manifests, cached native features, fold assignments, recipe predictions, weights, scripts, deployment receipt, and rejected Hybrid results are retained on the HQ SSD at `/Volumes/UFO-Work/field/model-audit-20261117/`. The prospective recording holdout remains separate and unmodified. No source training frames, labels, recordings, or reviewed archive packages were deleted.
