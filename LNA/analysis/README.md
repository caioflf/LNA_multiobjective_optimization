# Optimization Analysis

These scripts analyze optimizer outputs without modifying the optimization flow.
They read `optimization_history.jsonl` as a snapshot, so they can be used after
a run finishes or while a run is still appending results.

Run the analysis through `make` from the repository root.

Print a summary only:

```sh
make analysis-summary
```

Export CSV/JSON reports:

```sh
make analysis-export
```

Create metric-pair PNG plots:

```sh
make analysis-plots
```

Create per-generation 2D Pareto-frontier snapshots. By default this uses
`generations/generation_XXXX.json` files so the current generation population
can be highlighted while the Pareto frontier is computed from all history
records available up to that generation:

```sh
make analysis-pareto-evolution
```

Use history-only mode when the current population overlay is not needed or
generation files are unavailable:

```sh
make analysis-pareto-evolution \
  ANALYSIS_PARETO_EVOLUTION_GENERATION_SOURCE=history
```

Shade a constrained region without filtering any plotted data:

```sh
make analysis-pareto-evolution \
  ANALYSIS_MAX_NF_DB=10 \
  ANALYSIS_MIN_S21_DB=0
```

Compare the Pareto-frontier evolution of two or more runs:

```sh
make analysis-pareto-evolution-compare \
  ANALYSIS_PARETO_COMPARE_RUNS="optimized_circuits_6_0.9_0.15 mopso_archive" \
  ANALYSIS_PARETO_COMPARE_LABELS="NSGA MOPSO" \
  ANALYSIS_MAX_NF_DB=10 \
  ANALYSIS_MIN_S21_DB=0
```

Create an animation from a generated snapshot directory:

```sh
make analysis-pareto-animation
```

Export reports and plots:

```sh
make analysis-all
```

Remove generated analysis reports, plots, and local analysis caches:

```sh
make clean-analysis
```

Use a different optimization run or output location:

```sh
make analysis-all \
  ANALYSIS_RUN_ROOT=optimized_circuits \
  ANALYSIS_OUTPUT_DIR=analysis/results \
  ANALYSIS_PLOTS_DIR=analysis/plots
```

Apply post-processing filters:

```sh
make analysis-all \
  ANALYSIS_MIN_S21_DB=0 \
  ANALYSIS_MAX_S11_DB=-10 \
  ANALYSIS_MAX_NF_DB=5 \
  ANALYSIS_MAX_POWER_DBM=5 \
  ANALYSIS_MIN_F_BW=1
```

Available Make parameters:

- `ANALYSIS_RUN_ROOT`: optimization output directory to read. Default: current `OPT_OUTPUT_ROOT`.
- `ANALYSIS_OUTPUT_DIR`: CSV/JSON report directory. Default: `$(ANALYSIS_RUN_ROOT)/analysis/results`.
- `ANALYSIS_PLOTS_DIR`: PNG plot directory. Default: `$(ANALYSIS_RUN_ROOT)/analysis/plots`.
- `ANALYSIS_PARETO_EVOLUTION_DIR`: Pareto evolution PNG root. Default: `$(ANALYSIS_RUN_ROOT)/analysis/pareto_evolution`.
- `ANALYSIS_PARETO_EVOLUTION_PAIRS`: metric pairs for evolution snapshots. Use `NF_db:S21_db`, comma-separated pairs, or `all`. Default: `NF_db:S21_db`.
- `ANALYSIS_PARETO_EVOLUTION_EVERY`: plot every N inferred generations. Default: `1`.
- `ANALYSIS_PARETO_EVOLUTION_SCOPE`: history records used to compute the 2D frontier, `all` or `valid`. Default: `all`.
- `ANALYSIS_PARETO_EVOLUTION_MAX_GENERATIONS`: optional maximum inferred generation to plot.
- `ANALYSIS_PARETO_EVOLUTION_INCLUDE_PARTIAL`: set to `1` to include an unfinished current generation. Default: `0`.
- `ANALYSIS_PARETO_EVOLUTION_HIDE_VALID`: set to `1` to avoid highlighting valid records separately. Default: `1`.
- `ANALYSIS_PARETO_EVOLUTION_FILTER_CONSTRAINTS`: set to `1` to filter records by the analysis constraints before computing the frontier. Set to `0` to keep every plotted record visible. Default: `0`.
- `ANALYSIS_PARETO_EVOLUTION_SHADE_CONSTRAINTS`: set to `1` to shade the region allowed by constraints that apply directly to the plotted axes. If the plotted pair has no matching constraint axis, no shaded region is drawn. Default: `1`.
- `ANALYSIS_PARETO_EVOLUTION_SHADE_FRONTIER_REGION`: set to `1` to shade the dominated area implied by the 2D Pareto frontier. The shaded area is built from non-overlapping rectangles, not line interpolation. Default: `1`.
- `ANALYSIS_PARETO_EVOLUTION_FRONTIER_REGION_ALPHA`: opacity for the shaded frontier dominated area. Default: `0.1`.
- `ANALYSIS_PARETO_EVOLUTION_GENERATION_SOURCE`: `files`, `auto`, or `history`. `files` requires `generation_XXXX.json` files and uses them to highlight each current generation `population`; the frontier is still computed from history records up to that generation's `evaluations` count. `history` computes the same cumulative frontier without the population overlay. Default: `files`.
- `ANALYSIS_PARETO_EVOLUTION_GENERATIONS_DIR`: optional directory containing `generation_XXXX.json` files. Default: `$(ANALYSIS_RUN_ROOT)/generations`.
- `ANALYSIS_PARETO_EVOLUTION_HIDE_GENERATION_POPULATION`: set to `1` to hide the highlighted current generation population/particles. Default: `0`.
- `ANALYSIS_PARETO_COMPARE_RUNS`: two or more run roots to overlay in pareto-evolution comparison plots. Default: `$(ANALYSIS_COMPARE_RUNS)`.
- `ANALYSIS_PARETO_COMPARE_LABELS`: optional labels for the compared run roots. Provide one label per run.
- `ANALYSIS_PARETO_COMPARE_OUTPUT_DIR`: comparison PNG root. Default: `analysis/pareto_evolution_compare`.
- `ANALYSIS_PARETO_COMPARE_PAIRS`: metric pairs for comparison snapshots. Default: `$(ANALYSIS_PARETO_EVOLUTION_PAIRS)`.
- `ANALYSIS_PARETO_COMPARE_EVERY`: plot every N inferred generations for comparison snapshots. Default: `$(ANALYSIS_PARETO_EVOLUTION_EVERY)`.
- `ANALYSIS_PARETO_COMPARE_SCOPE`: history records used to compute each run's 2D frontier, `all` or `valid`. Default: `$(ANALYSIS_PARETO_EVOLUTION_SCOPE)`.
- `ANALYSIS_PARETO_COMPARE_GENERATION_MODE`: `common` plots only generations present in every run; `union` plots every generation present in at least one run. Default: `common`.
- `ANALYSIS_PARETO_COMPARE_MAX_GENERATIONS`: optional maximum inferred generation to plot. Default: `$(ANALYSIS_PARETO_EVOLUTION_MAX_GENERATIONS)`.
- `ANALYSIS_PARETO_COMPARE_INCLUDE_PARTIAL`: set to `1` to include unfinished current generations. Default: `$(ANALYSIS_PARETO_EVOLUTION_INCLUDE_PARTIAL)`.
- `ANALYSIS_PARETO_COMPARE_HIDE_HISTORY`: set to `1` to hide per-run history scatter points. Default: `0`.
- `ANALYSIS_PARETO_COMPARE_HIDE_VALID`: set to `1` to avoid highlighting valid records separately. Default: `$(ANALYSIS_PARETO_EVOLUTION_HIDE_VALID)`.
- `ANALYSIS_PARETO_COMPARE_FILTER_CONSTRAINTS`: set to `1` to filter records by the analysis constraints before computing frontiers. Default: `$(ANALYSIS_PARETO_EVOLUTION_FILTER_CONSTRAINTS)`.
- `ANALYSIS_PARETO_COMPARE_SHADE_CONSTRAINTS`: set to `1` to shade the constrained region on matching plotted axes. Default: `$(ANALYSIS_PARETO_EVOLUTION_SHADE_CONSTRAINTS)`.
- `ANALYSIS_PARETO_COMPARE_SHADE_FRONTIER_REGION`: set to `1` to shade each run's 2D Pareto-frontier dominated area. Default: `$(ANALYSIS_PARETO_EVOLUTION_SHADE_FRONTIER_REGION)`.
- `ANALYSIS_PARETO_COMPARE_FRONTIER_REGION_ALPHA`: opacity for each run's shaded frontier dominated area. Default: `$(ANALYSIS_PARETO_EVOLUTION_FRONTIER_REGION_ALPHA)`.
- `ANALYSIS_PARETO_COMPARE_GENERATION_SOURCE`: `auto`, `files`, or `history` for comparison snapshots. Default: `$(ANALYSIS_PARETO_EVOLUTION_GENERATION_SOURCE)`.
- `ANALYSIS_PARETO_COMPARE_GENERATIONS_DIRS`: optional generation directories, one per run root. Default: each run's `generations` directory.
- `ANALYSIS_PARETO_COMPARE_HIDE_GENERATION_POPULATION`: set to `1` to hide highlighted populations/particles in comparison snapshots. Default: `$(ANALYSIS_PARETO_EVOLUTION_HIDE_GENERATION_POPULATION)`.
- `ANALYSIS_ANIMATION_PAIR`: snapshot pair directory name to animate. Default: `nf_db_vs_s21_db`.
- `ANALYSIS_ANIMATION_INPUT_DIR`: PNG frame directory. Default: `$(ANALYSIS_PARETO_EVOLUTION_DIR)/$(ANALYSIS_ANIMATION_PAIR)`.
- `ANALYSIS_ANIMATION_OUTPUT`: GIF or MP4 output path. Default: `$(ANALYSIS_PARETO_EVOLUTION_DIR)/$(ANALYSIS_ANIMATION_PAIR).gif`.
- `ANALYSIS_ANIMATION_FPS`: animation frames per second. Default: `20`.
- `ANALYSIS_ANIMATION_ENGINE`: `auto`, `ffmpeg`, or `pillow`. Default: `auto`.
- `ANALYSIS_PYTHON`: Python used for summaries/exports. Default: `python3`.
- `ANALYSIS_PLOT_PYTHON`: Python used for matplotlib plots. Default: `/opt/homebrew/bin/python3`.
- `ANALYSIS_COLOR_BY`: plot color axis. Use metrics (`NF_db`, `NFmin_db`, `power_dBm`, `S21_db`, `F_BW`, `S11_db`), transistor values/indexes (`vg`, `wtot_um`, `length_um`, `device_type_index`, `vt_index`, `wtot_index`, `length_index`), or passive indexes like `gate_l_index`, `source_l_index`, `load_c_index`, `feedback_c_index`. Short forms like `feedback_c` also work. Default: `vg`.
- `ANALYSIS_TOP_COUNT`: number of ranked candidates to export. Default: `1000`.
- `ANALYSIS_MAX_NF_DB`: keep records with `NF_db <= value`.
- `ANALYSIS_MAX_POWER_DBM`: keep records with `power_dBm <= value`.
- `ANALYSIS_MAX_POWER`: alias for `ANALYSIS_MAX_POWER_DBM`.
- `ANALYSIS_MIN_S21_DB`: keep records with `S21_db >= value`.
- `ANALYSIS_MIN_F_BW`: keep records with `F_BW >= value`.
- `ANALYSIS_MAX_S11_DB`: keep records with `S11_db <= value`.
- `ANALYSIS_CLEAN_PATHS`: paths removed by `make clean-analysis`. Default: generated `analysis/results*`, `analysis/plots*`, and analysis cache folders.

The summarizer writes these files when `ANALYSIS_OUTPUT_DIR` is used:

- `evaluations.csv`
- `valid_evaluations.csv`
- `filtered_valid_evaluations.csv`
- `pareto_front.csv`
- `filtered_pareto_front.csv`
- `shortlist.csv`
- `shortlist.json`
- `ranked_candidates.csv`
- `ranked_candidates.json`
- `report.json`

The plot script writes PNG files to `ANALYSIS_PLOTS_DIR` and requires
`matplotlib`. On this machine, `/opt/homebrew/bin/python3` already has
matplotlib available.

Pareto evolution snapshots are written one directory per metric pair, for
example:

```text
$(ANALYSIS_RUN_ROOT)/analysis/pareto_evolution/nf_db_vs_s21_db/generation_0000.png
```

Comparison snapshots use the same per-pair directory layout under
`ANALYSIS_PARETO_COMPARE_OUTPUT_DIR`. Each frame overlays the current 2D
frontier from each run at the same generation number.

The plotted frontier is recomputed from `optimization_history.jsonl` records
available up to each generation's `evaluations` count. The saved `population`
field in each `generation_XXXX.json` file is used only to highlight the current
population/particles. For MOPSO this highlight is the current swarm; for NSGA
it is the current population. The saved `current_pareto` field is not used by
these plots.

Frontier area shading uses the dominated rectangles implied by each plotted
pair's minimize or maximize directions, so it follows the same square method
used for 2D area calculation. The plotted frontier line uses the same staircase
boundary instead of interpolating diagonally between Pareto points.

Those snapshots can later be compiled into an animation with a tool such as
`ffmpeg`, or directly through:

```sh
make analysis-pareto-animation \
  ANALYSIS_ANIMATION_PAIR=nf_db_vs_s21_db \
  ANALYSIS_ANIMATION_OUTPUT=mopso_archive/analysis/pareto_evolution/nf_db_vs_s21_db.gif
```

MP4 output requires `ffmpeg`. GIF output can use Pillow when `ffmpeg` is not
available.
