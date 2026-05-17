# AndroCT--KronoDroid Protocol Alignment Check

Date: 2026-05-16

## Status

AndroCT is positioned as the second main emulator-real benchmark, not as a small external check.
The running hzt3 experiment under `/root/experiments/androct_second_main` executes the same
claim-driven feature-group reliability audit used for the KronoDroid main story.

## Matched Core Protocol

The AndroCT runner matches the KronoDroid reliability-audit protocol on the following axes:

- Emulator-to-real and real-to-emulator directions.
- Fixed feature-group baselines for Android API, Java API, intent, and all-platform views.
- Source-CV selected group.
- Uniform ensemble.
- Source-CV softmax ensemble.
- Support-gated softmax ensemble at tau = 0.05 and tau = 0.10.
- Permuted-support softmax control.
- Top-1 support-selected group.
- Ten paired seeds.
- Balanced accuracy, macro-F1, and accuracy in summary outputs.
- Support-budget sweep over K = 1, 2, 3, 5, and 10.

The running grid contains 55 jobs:

- 10 yearly AndroCT benchmarks for 2010--2019 times 5 K values = 50 jobs.
- 5 pooled 2010--2019 benchmarks for K = 1, 2, 3, 5, and 10.

Each job evaluates both directions, so the yearly grid covers 100 year/K/direction cells plus
10 pooled/K/direction cells.

## What Is Not Identical

The experiments are not literally identical in dataset shape:

- KronoDroid has the paper's canonical binary/family task structure and the severe metadata failure case.
- AndroCT is a decade-scale year-wise emulator-real benchmark; the main comparison is year-wise reliability
  recovery and pooled boundary diagnosis.
- KronoDroid includes additional auxiliary diagnostics such as stronger all-feature baselines and adaptation
  checks. These are not part of the current AndroCT 55-job grid unless explicitly added later.

Therefore, the correct paper wording is:

> AndroCT repeats the main feature-group reliability audit protocol as a second main emulator-real benchmark.

Avoid claiming:

> AndroCT repeats every auxiliary KronoDroid diagnostic or proves SGFE uniformly beats all baselines.

## Claim Boundary

Allowed after the current 55-job run completes:

- AndroCT is a second main emulator-real benchmark.
- The same reliability-audit protocol is applied to AndroCT.
- Results can support year-wise reliability recovery, K-budget sensitivity, support-label controls, and
  pooled-vs-year-wise boundary diagnosis.

Not allowed unless additional experiments are added:

- All KronoDroid auxiliary stronger-classifier/adaptation diagnostics are replicated on AndroCT.
- SGFE uniformly dominates uniform/source-CV ensembles on AndroCT.
