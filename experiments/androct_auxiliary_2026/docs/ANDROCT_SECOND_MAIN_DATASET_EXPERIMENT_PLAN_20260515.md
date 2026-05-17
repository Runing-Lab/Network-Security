# AndroCT as the Second Main Dataset: Experiment Plan

Date: 2026-05-15

Target paper: CIKM 2026 submission, "Auditing Feature-Group Reliability in Android Malware Data Mining under Runtime Shift"

## Positioning

AndroCT should be treated as the second main emulator-real benchmark, not merely as an external stress test. Its role is different from KronoDroid:

- KronoDroid: canonical emulator-real benchmark that demonstrates a severe source-CV feature-group failure and the main corrective result.
- AndroCT: decade-scale emulator-real benchmark that tests whether feature-group reliability auditing persists across 2010--2019 year-specific runtime shifts.
- CICAndMal2020: secondary runtime-phase pilot, not a main emulator-real replication.

The AndroCT headline should not be "SGFE wins pooled accuracy." The correct headline is:

> AndroCT shows that target-support reliability auditing improves over fixed all-platform views in most year-direction cells and identifies year-specific reliable groups, while pooled decade mixtures expose a boundary where uniform or source-CV weighting can be stronger.

## Already Available Evidence

Current completed AndroCT v2 results support the following claims:

- Year-wise reliability recovery: SGFE at tau=0.10 improves over fixed all-platform in 19 of 20 year-direction cells.
- Conservative pooled boundary: pooled 2010--2019 results favor uniform/source-CV over SGFE.
- Strong failure case: 2017 emulator-to-real has fixed all-platform/uniform/source-CV near 0.54 BA, Java API near 0.969 BA, and SGFE partially recovers to about 0.874 with high variance.
- Main caveat: SGFE loses to uniform in many year-direction cells, so the claim must be reliability recovery against fixed all-platform and boundary diagnosis, not universal superiority.

Available files:

- `05_results/androct_v2_analysis/androct_v2_yearly_key_metrics.md`
- `05_results/androct_v2_analysis/androct_v2_yearly_key_metrics.csv`
- `05_results/androct_v2_analysis/androct_v2_combined_2010_2019_summary.md`
- `05_results/androct_v2_analysis/androct_v2_combined_2010_2019_summary.csv`

## Minimum Additional Experiments Needed

To fully elevate AndroCT to a second main dataset, run or verify the same claim-driven controls used for KronoDroid.

### A1. AndroCT per-year full protocol

For each year 2010--2019 and both directions:

- Emu -> Real
- Real -> Emu

Run:

- Fixed Android API group
- Fixed Java API group
- Fixed Intent group
- Fixed all-platform group
- Oracle best fixed group, analysis-only
- Source-CV selected group
- Uniform ensemble
- Source-CV softmax ensemble
- SGFE at tau=0.05
- SGFE at tau=0.10
- Permuted-support SGFE
- Top-1 support-selected group

Seeds:

- 10 paired seeds minimum, matching current v2.
- Keep identical support/query splits across compared methods.

Primary metrics:

- Balanced accuracy
- Macro-F1
- Per-year paired wins/losses
- Wilcoxon signed-rank test where seed-aligned records exist

### A2. AndroCT support-label causality

Purpose: prove that target labels carry real signal on AndroCT, not just support composition.

For each year-direction cell:

- True-support SGFE vs permuted-support SGFE
- Report mean delta, paired wins, Wilcoxon p-value
- Aggregate over 20 year-direction cells:
  - number of cells where true support wins
  - median true-minus-permuted BA
  - worst-case cells

Expected paper use:

- If true support beats permuted support in most cells, AndroCT becomes strong causal evidence.
- If not, AndroCT remains a boundary dataset and should be framed conservatively.

### A3. AndroCT soft weighting versus top-1

Purpose: test whether soft aggregation is still useful in decade-scale shifts.

Compare:

- SGFE tau=0.05
- SGFE tau=0.10
- Top-1 support-selected group
- Uniform ensemble

Report:

- cells where soft SGFE beats top-1
- cells where top-1 is better
- whether soft weighting reduces high-variance year failures

Expected paper use:

- If soft wins: supports method design beyond single-group selection.
- If top-1 wins: revise method claim to "support scoring identifies reliable groups" more than "soft ensemble is optimal."

### A4. AndroCT K-budget sensitivity

Purpose: align AndroCT with KronoDroid K=2/K=3/K=5 discussion.

Run for K in:

- K=1
- K=2
- K=3
- K=5
- K=10 if data support is sufficient

For each K:

- SGFE tau=0.05 and tau=0.10
- Permuted support
- Top-1 support
- Uniform ensemble

Report:

- support-label budget per year-direction cell
- BA/F1 mean and standard deviation
- stability of support weights

Expected paper use:

- Shows whether AndroCT requires more labels than KronoDroid because each year has different feature reliability.

### A5. AndroCT pooled versus year-wise explanation

Purpose: explain why pooled decade mixtures hurt SGFE.

Analyze:

- per-year best group distribution
- support-weight entropy per year
- pooled support-weight entropy
- variance of support scores across years
- cells where pooled support labels disagree with year-specific reliable groups

Deliverables:

- one compact table: year, best fixed group, SGFE weight top group, SGFE-minus-fixed, SGFE-minus-uniform
- one figure: year-wise reliability recovery and pooled boundary, current Fig. 10 can be extended

Expected paper use:

- Converts "pooled loss" from a weakness into a boundary-condition result.

## Paper Revision Plan

### Manuscript structure

Recommended Section 4 structure:

1. Experimental setup and protocol
2. KronoDroid source-CV failure and recovery
3. KronoDroid support signal and ablations
4. AndroCT decade-scale emulator-real benchmark
5. Adaptation and stronger-classifier diagnostics
6. CICAndMal2020 secondary runtime-phase pilot

If page budget is tight, keep CICAndMal2020 as a short paragraph/table and move detailed CIC notes to artifact.

### AndroCT claims allowed now

Allowed now:

- AndroCT is a complete emulator-real dataset and can be treated as a second main benchmark.
- SGFE improves over fixed all-platform in most year-direction cells.
- AndroCT reveals boundary conditions: pooled decade mixtures can favor uniform/source-CV weighting.
- 2017 E->R shows a strong year-specific reliable-group failure case.

Not allowed yet without more controls:

- SGFE is uniformly better than label-free ensembles on AndroCT.
- SGFE's AndroCT gains are caused by correct support labels rather than support composition.
- Soft weighting is always better than top-1 on AndroCT.
- K=5 is sufficient for all AndroCT year-direction cells.

## Priority Order

1. Fix factual consistency in current paper.
2. Reframe AndroCT as second main benchmark with conservative claims.
3. Run A2 true-vs-permuted support on all year-direction cells.
4. Run A3 top-1 vs soft weighting.
5. Run A4 K-budget sensitivity.
6. Run A5 pooled-vs-year-wise analysis.
7. Update Fig. 10 and Table 4 to show AndroCT as a main result rather than a small external check.

## Acceptance-Risk Rationale

Making AndroCT the second main dataset can improve the CIKM story if the paper is careful:

- It answers the "single primary dataset" criticism.
- It keeps the manuscript honest about pooled failures.
- It strengthens the paper's identity as data-mining reliability analysis rather than a one-dataset security case study.

The risk is that reviewers may focus on the pooled loss. The paper must therefore emphasize year-wise reliability recovery and boundary diagnosis as the AndroCT contribution.
