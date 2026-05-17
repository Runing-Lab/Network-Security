# AndroCT Auxiliary Experiment Process

Date: 2026-05-17

## Goal

Replicate the KronoDroid auxiliary experiment suite on AndroCT after the
AndroCT second-main 55-job run completed. The purpose is to support AndroCT as
a true second main dataset with the same style of reviewer-facing controls.

## Confirmed Starting State

- AndroCT second-main run completed 55/55 tasks.
- Final main results were synchronized to:
  `G:\CIKM2026_network_agent_safety_package_20260515_134609\06_androct_second_main_final_results_hzt3_20260517_075809`
- The replacement server is accessed by SSH key only:
  `ssh -i <SSH_KEY_PATH> -p <PORT> <USER>@<HOST>`
- Remote main directory:
  `/root/experiments/androct_second_main`
- Remote auxiliary directory:
  `/root/experiments/androct_auxiliary`

## Auxiliary Blocks

The AndroCT auxiliary script mirrors the KronoDroid auxiliary questions while
respecting AndroCT's logcat text representation.

1. `source_plus_support_warm_start`
   - Trains all-platform source plus target-support models.
   - Mirrors KronoDroid source-plus-support warm-start evidence.

2. `allfeature_support_selection`
   - Trains all-platform source-only candidate models.
   - Uses the same labeled support set only to select a candidate.
   - Mirrors all-feature support-selection baseline.

3. `support_only_target_baseline`
   - Trains only on the K-per-class target support set.
   - Tests whether tiny target supervision alone explains the result.

4. `label_noise_support_signal`
   - Corrupts support labels at controlled rates before support weighting.
   - Mirrors label-noise/support-corruption stress tests.

5. `svd_diagonal_coral_da`
   - Runs a zero-target-label SVD plus diagonal-CORAL baseline on all-platform
     features.
   - Mirrors the CORAL-style adaptation diagnostics in a text-feature-safe way.

## Task Grid

The auxiliary grid matches the AndroCT second-main grid:

- Yearly tasks: 2010-2019.
- Pooled task: 2010-2019 combined.
- K values: 1, 2, 3, 5, 10.
- Total task folders: 55.
- Splits inside each task: emulator-to-real and real-to-emulator.
- Seeds inside each task: 0-9.

## Scripts Created

- `F:\work\submissions\network_agent_safety\scripts\run_androct_auxiliary_experiments.py`
- `F:\work\submissions\network_agent_safety\scripts\launch_androct_auxiliary_hzt3.sh`
- `F:\work\submissions\network_agent_safety\scripts\monitor_androct_auxiliary_hzt3.sh`
- `F:\work\submissions\network_agent_safety\scripts\pull_androct_auxiliary_results_hzt3.ps1`

## Run Log

### 2026-05-17

- Wrote the AndroCT auxiliary experiment script.
- Wrote the remote queue launcher with `MAX_PARALLEL` control.
- Wrote the remote monitor script.
- Wrote the final pull/sync script for G-drive packaging.
- Deployed scripts to `/root/experiments/androct_auxiliary/scripts`.
- Remote syntax checks passed for the Python auxiliary script and shell launch/monitor scripts.
- Ran a minimal smoke test on year 2010, K=1, seed 0, emulator-to-real, warm-start only. It produced records, summary CSV, summary MD, and raw summary CSV.
- Moved smoke outputs out of formal `outputs/` so they are not counted as part of the 55 formal tasks.
- Started the full auxiliary queue with `MAX_PARALLEL=8`.
- Initial running tasks after full launch:
  - `androct_aux_y2010_k1`
  - `androct_aux_y2010_k2`
  - `androct_aux_y2010_k3`
  - `androct_aux_y2010_k5`
  - `androct_aux_y2010_k10`
  - `androct_aux_y2011_k1`
  - `androct_aux_y2011_k2`
  - `androct_aux_y2011_k3`
- Updated the heartbeat automation to monitor the auxiliary phase, restart the launcher if needed, pull lightweight live snapshots, and perform final G-drive sync when 55/55 formal summaries are complete.
- Copied the control scripts and this process document to:
  `G:\CIKM2026_network_agent_safety_package_20260515_134609\07_androct_auxiliary_experiment_control`

### 2026-05-17 pooled acceleration

- The original pooled auxiliary tail was too coarse: five monolithic tasks
  `androct_aux_y2010_2019_k1/k2/k3/k5/k10` each had to run both splits and all
  seeds serially.
- Added pooled-shard acceleration scripts:
  - `merge_androct_auxiliary_shards.py`
  - `launch_androct_auxiliary_pooled_shards_hzt3.sh`
  - `accelerate_androct_pooled_hzt3.sh`
- Executed the acceleration switch on hzt3:
  - Stopped old monolithic pooled tmux tasks.
  - Archived partial monolithic outputs under
    `/root/experiments/androct_auxiliary/pooled_monolith_partial_20260517T143015Z`.
  - Started shard launcher under
    `/root/experiments/androct_auxiliary/state/pooled_shard_launcher.pid`.
  - New shard grid: 5 K values x 2 splits x 10 seeds = 100 shard tasks.
  - Each K is merged back into the original formal output directory after its
    20 shards complete, preserving the final 55-summary counting protocol.
- Initial `MAX_PARALLEL=6` caused an exit 137 on one shard, indicating memory
  pressure/OOM.
- Reduced pooled shard parallelism to `MAX_PARALLEL=4`.
- Confirmed the old monolithic launcher is stopped and only shard sessions
  remain.
