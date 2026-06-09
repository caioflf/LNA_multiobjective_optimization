PYTHON ?= python3

PASSIVE_NETWORK_SCRIPT := src/scripts/passive_networks.py
PASSIVE_NETWORK_MULTI_OBJECTIVE_DB := src/database/passive_networks_mim_no_varactors.json
MIM_MODELS ?= sky130_fd_pr__cap_mim_m3_2
MIM_SIZES ?= 2x2 4x4 6x6 8x8 10x10
MIM_MF_VALUES ?= 1
POLY_RESISTOR_SELECTION ?= all
PASSIVE_NETWORK_TOPOLOGY ?= rlc-parallel
PASSIVE_MAX_RESISTORS_PER_NETWORK ?=

SIMULATE_CIRCUITS_SCRIPT := src/scripts/simulate_circuits.py
OPTIMIZE_CIRCUITS_SCRIPT := src/scripts/optimize_circuits.py
OPTIMIZE_CIRCUITS_MOPSO_SCRIPT := src/scripts/optimize_circuits_mopso.py
CIRCUIT_DATABASE_SCRIPT := src/scripts/build_circuit_database.py
CIRCUIT_OUTPUT_ROOT ?= generated_circuits
CIRCUIT_DATABASE_OUTPUT ?= data/circuit_database/circuits.sqlite
CIRCUIT_DATABASE_RUNS ?= $(OPT_OUTPUT_ROOT) \
												 mopso_archive \
												 $(OPT_OUTPUT_ROOT)_unconstrained \
												 optimized_circuits_mopso_constrained_backup
CIRCUIT_DATABASE_OVERWRITE ?= 0
CIRCUIT_DATABASE_SKIP_MISSING ?= 1

SIM_THREADS ?= 6
SIM_PRIORITY ?= high
SIM_MAX_CIRCUITS ?=
SIM_SUBSET ?=
SIM_PROGRESS ?= 1
SIM_PROGRESS_EVERY ?= 1
SIM_TIMEOUT ?=


OPT_PARTITIONS := 6
OPT_CROSSOVER_PROB := 0.9
OPT_MUTATION_PROB := 0.15
OPT_VERSION := $(OPT_PARTITIONS)_$(OPT_CROSSOVER_PROB)_$(OPT_MUTATION_PROB)
OPT_OUTPUT_ROOT := optimized_circuits_$(OPT_VERSION)_unconstrained
OPT_TRANSISTOR_GROUP ?= nmos
OPT_POPULATION_SIZE ?= 300
OPT_OFFSPRING_SIZE ?= 300
OPT_GENERATIONS ?= 400
OPT_F0 ?= 5e9
OPT_AC_START ?=
OPT_AC_STOP ?=
OPT_RESUME_FROM ?=
OPT_RESUME_IN_PLACE ?= 
OPT_OVERWRITE_OUTPUT ?=
OPT_SIM_THREADS ?= 6
OPT_SIM_TIMEOUT ?= 180
OPT_DEMO_SIM_TIMEOUT ?= 120
OPT_CIRCUIT_DATABASE ?= $(CIRCUIT_DATABASE_OUTPUT)
OPT_SEED ?= 7
OPT_MAX_NF_DB ?=
OPT_MAX_POWER_DBM ?= 
OPT_MIN_S21_DB ?=
OPT_MIN_F_BW ?= 
OPT_MAX_S11_DB ?= 

MOPSO_OUTPUT_ROOT ?= optimized_circuits_mopso_unconstrained
MOPSO_TRANSISTOR_GROUP ?= nmos
MOPSO_SWARM_SIZE ?= 300
MOPSO_ITERATIONS ?= 400
MOPSO_ARCHIVE_SIZE ?= 300
MOPSO_ARCHIVE_PARTITIONS ?= 6
MOPSO_INERTIA_WEIGHT ?= 0.6
MOPSO_COGNITIVE_WEIGHT ?= 1.5
MOPSO_SOCIAL_WEIGHT ?= 1.5
MOPSO_VELOCITY_CLAMP ?= 0.5
MOPSO_MUTATION_PROB ?= 0.05
MOPSO_F0 ?= 5e9
MOPSO_AC_START ?=
MOPSO_AC_STOP ?=
MOPSO_OVERWRITE_OUTPUT ?=
MOPSO_SIM_THREADS ?= 6
MOPSO_SIM_TIMEOUT ?= 180
MOPSO_DEMO_SIM_TIMEOUT ?= 120
MOPSO_CIRCUIT_DATABASE ?= $(CIRCUIT_DATABASE_OUTPUT)
MOPSO_SEED ?= 7
MOPSO_MAX_NF_DB ?=
MOPSO_MAX_POWER_DBM ?=
MOPSO_MIN_S21_DB ?=
MOPSO_MIN_F_BW ?=
MOPSO_MAX_S11_DB ?=

#ANALYSIS_RUN_ROOT ?= mopso_archive
ANALYSIS_RUN_ROOT ?= $(MOPSO_OUTPUT_ROOT)
#ANALYSIS_RUN_ROOT ?= $(OPT_OUTPUT_ROOT)
#ANALYSIS_RUN_ROOT ?= optimized_circuits_6_0.9_0.15
ANALYSIS_OUTPUT_DIR ?= $(ANALYSIS_RUN_ROOT)/analysis/results
ANALYSIS_PYTHON ?= $(PYTHON)
ANALYSIS_PLOT_PYTHON ?= /opt/homebrew/bin/python3
#ANALYSIS_COLOR_BY ?= feedback_c
ANALYSIS_COLOR_BY ?= wtot_um
#ANALYSIS_COLOR_BY ?= length_um
#ANALYSIS_COLOR_BY ?= vg
#ANALYSIS_COLOR_BY ?= gate_l
ANALYSIS_PLOTS_DIR ?= $(ANALYSIS_RUN_ROOT)/analysis/plots/$(ANALYSIS_COLOR_BY)
ANALYSIS_HISTORY_PLOTS_DIR ?= $(ANALYSIS_RUN_ROOT)/analysis/plots_history/$(ANALYSIS_COLOR_BY)
ANALYSIS_PARETO_EVOLUTION_DIR ?= $(ANALYSIS_RUN_ROOT)/analysis/pareto_evolution
ANALYSIS_PARETO_EVOLUTION_PAIRS ?= NF_db:S21_db,S21_db:power_dBm 
ANALYSIS_PARETO_EVOLUTION_EVERY ?= 5
ANALYSIS_PARETO_EVOLUTION_SCOPE ?= all
ANALYSIS_PARETO_EVOLUTION_MAX_GENERATIONS ?=
ANALYSIS_PARETO_EVOLUTION_INCLUDE_PARTIAL ?= 0
ANALYSIS_PARETO_EVOLUTION_HIDE_VALID ?= 1
ANALYSIS_PARETO_EVOLUTION_FILTER_CONSTRAINTS ?= 0
ANALYSIS_PARETO_EVOLUTION_SHADE_CONSTRAINTS ?= 1
ANALYSIS_PARETO_EVOLUTION_SHADE_FRONTIER_REGION ?= 1
ANALYSIS_PARETO_EVOLUTION_FRONTIER_REGION_ALPHA ?= 0.1
ANALYSIS_PARETO_EVOLUTION_GENERATION_SOURCE ?= files
ANALYSIS_PARETO_EVOLUTION_GENERATIONS_DIR ?=
ANALYSIS_PARETO_EVOLUTION_HIDE_GENERATION_POPULATION ?= 0
ANALYSIS_PARETO_COMPARE_RUNS ?= $(ANALYSIS_COMPARE_RUNS)
ANALYSIS_PARETO_COMPARE_LABELS ?= NGSA_C MOPSO_C
ANALYSIS_PARETO_COMPARE_OUTPUT_DIR ?= analysis/pareto_evolution_compare
ANALYSIS_PARETO_COMPARE_PAIRS ?= $(ANALYSIS_PARETO_EVOLUTION_PAIRS)
ANALYSIS_PARETO_COMPARE_EVERY ?= $(ANALYSIS_PARETO_EVOLUTION_EVERY)
ANALYSIS_PARETO_COMPARE_SCOPE ?= $(ANALYSIS_PARETO_EVOLUTION_SCOPE)
ANALYSIS_PARETO_COMPARE_GENERATION_MODE ?= common
ANALYSIS_PARETO_COMPARE_MAX_GENERATIONS ?= $(ANALYSIS_PARETO_EVOLUTION_MAX_GENERATIONS)
ANALYSIS_PARETO_COMPARE_INCLUDE_PARTIAL ?= $(ANALYSIS_PARETO_EVOLUTION_INCLUDE_PARTIAL)
ANALYSIS_PARETO_COMPARE_HIDE_HISTORY ?= 0
ANALYSIS_PARETO_COMPARE_HIDE_VALID ?= $(ANALYSIS_PARETO_EVOLUTION_HIDE_VALID)
ANALYSIS_PARETO_COMPARE_FILTER_CONSTRAINTS ?= $(ANALYSIS_PARETO_EVOLUTION_FILTER_CONSTRAINTS)
ANALYSIS_PARETO_COMPARE_SHADE_CONSTRAINTS ?= $(ANALYSIS_PARETO_EVOLUTION_SHADE_CONSTRAINTS)
ANALYSIS_PARETO_COMPARE_SHADE_FRONTIER_REGION ?= $(ANALYSIS_PARETO_EVOLUTION_SHADE_FRONTIER_REGION)
ANALYSIS_PARETO_COMPARE_FRONTIER_REGION_ALPHA ?= $(ANALYSIS_PARETO_EVOLUTION_FRONTIER_REGION_ALPHA)
ANALYSIS_PARETO_COMPARE_GENERATION_SOURCE ?= $(ANALYSIS_PARETO_EVOLUTION_GENERATION_SOURCE)
ANALYSIS_PARETO_COMPARE_GENERATIONS_DIRS ?=
ANALYSIS_PARETO_COMPARE_HIDE_GENERATION_POPULATION ?= $(ANALYSIS_PARETO_EVOLUTION_HIDE_GENERATION_POPULATION)
ANALYSIS_ANIMATION_PAIR ?= nf_db_vs_s21_db
ANALYSIS_ANIMATION_INPUT_DIR ?= $(ANALYSIS_PARETO_EVOLUTION_DIR)/$(ANALYSIS_ANIMATION_PAIR)
ANALYSIS_ANIMATION_OUTPUT ?= $(ANALYSIS_PARETO_EVOLUTION_DIR)/$(ANALYSIS_ANIMATION_PAIR).gif
ANALYSIS_ANIMATION_FPS ?= 40
ANALYSIS_ANIMATION_ENGINE ?= auto
ANALYSIS_TOP_COUNT ?= 30000
ANALYSIS_MAX_NF_DB ?=  10
ANALYSIS_MAX_POWER_DBM ?=
ANALYSIS_MIN_S21_DB ?= 0
ANALYSIS_MIN_F_BW ?= 
ANALYSIS_MAX_S11_DB ?= 
ANALYSIS_COMPARE_RUNS ?= $(OPT_OUTPUT_ROOT) $(MOPSO_OUTPUT_ROOT) 
ANALYSIS_COMPARE_LABELS ?=
ANALYSIS_PERFORMANCE_OUTPUT_DIR ?= analysis/performance
ANALYSIS_HV_SAMPLES ?= 50000
ANALYSIS_HV_SEED ?= 1
ANALYSIS_GD_POWER ?= 2
ANALYSIS_PERFORMANCE_RECORD_SCOPE ?= all
ANALYSIS_CLEAN_PATHS ?= $(OPT_OUTPUT_ROOT)/analysis/results \
												$(OPT_OUTPUT_ROOT)/analysis/results_* \
												$(OPT_OUTPUT_ROOT)/analysis/plots \
												$(OPT_OUTPUT_ROOT)/analysis/plots_* \
												$(OPT_OUTPUT_ROOT)/analysis/pareto_evolution \
												$(ANALYSIS_RUN_ROOT)/analysis/pareto_evolution \
												$(ANALYSIS_PARETO_COMPARE_OUTPUT_DIR) \
												$(OPT_OUTPUT_ROOT)/analysis/.cache \
												$(OPT_OUTPUT_ROOT)/analysis/.matplotlib-cache \
												$(OPT_OUTPUT_ROOT)/analysis/__pycache__
ANALYSIS_FILTER_ARGS = $(strip \
	$(if $(ANALYSIS_MAX_NF_DB),--max-nf-db $(ANALYSIS_MAX_NF_DB)) \
	$(if $(ANALYSIS_MAX_POWER_DBM),--max-power-dbm $(ANALYSIS_MAX_POWER_DBM)) \
	$(if $(ANALYSIS_MIN_S21_DB),--min-s21-db $(ANALYSIS_MIN_S21_DB)) \
	$(if $(ANALYSIS_MIN_F_BW),--min-f-bw $(ANALYSIS_MIN_F_BW)) \
	$(if $(ANALYSIS_MAX_S11_DB),--max-s11-db $(ANALYSIS_MAX_S11_DB)) \
)
ANALYSIS_COMPARE_LABEL_ARGS = $(if $(ANALYSIS_COMPARE_LABELS),--labels $(ANALYSIS_COMPARE_LABELS))

.PHONY: all generate-passive-network-multiobjective clean-passive-network-multiobjective simulate-circuits analyze-circuits optimize-circuits optimize-circuits-demo optimize-circuits-mopso optimize-circuits-mopso-demo build-circuit-database append-circuit-database rebuild-circuit-database analysis-summary analysis-export analysis-plots analysis-plots-history analysis-pareto-evolution analysis-pareto-evolution-compare analysis-pareto-animation analysis-performance analysis-all analysis-plot-all analysis-plot-all-history clean-analysis clean-circuits

all: generate-passive-network-multiobjective

generate-passive-network-multiobjective: $(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB)

$(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB): $(PASSIVE_NETWORK_SCRIPT) src/database/capacitors.py src/database/inductors.py src/database/resistors.py
	$(PYTHON) $(PASSIVE_NETWORK_SCRIPT) \
		--no-varactors \
		--mim-models $(MIM_MODELS) \
		--mim-sizes $(MIM_SIZES) \
		--mf-values $(MIM_MF_VALUES) \
		--poly-resistor-selection $(POLY_RESISTOR_SELECTION) \
		--network-topology $(PASSIVE_NETWORK_TOPOLOGY) \
		$(if $(PASSIVE_MAX_RESISTORS_PER_NETWORK),--max-resistors-per-network $(PASSIVE_MAX_RESISTORS_PER_NETWORK),) \
		--output $(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB)

clean-passive-network-multiobjective:
	rm -f $(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB)

simulate-circuits: $(SIMULATE_CIRCUITS_SCRIPT)
	$(PYTHON) $(SIMULATE_CIRCUITS_SCRIPT) \
		$(CIRCUIT_OUTPUT_ROOT) \
		--threads $(SIM_THREADS) \
		--priority $(SIM_PRIORITY) \
		$(if $(SIM_SUBSET),--subset $(SIM_SUBSET),) \
		$(if $(SIM_MAX_CIRCUITS),--max-circuits $(SIM_MAX_CIRCUITS),) \
		$(if $(filter 0 false no,$(SIM_PROGRESS)),--no-progress,) \
		$(if $(SIM_PROGRESS_EVERY),--progress-every $(SIM_PROGRESS_EVERY),) \
		$(if $(SIM_TIMEOUT),--timeout $(SIM_TIMEOUT),)

analyze-circuits: $(SIMULATE_CIRCUITS_SCRIPT)
	$(PYTHON) $(SIMULATE_CIRCUITS_SCRIPT) \
		$(CIRCUIT_OUTPUT_ROOT) \
		--analyze-only \
		$(if $(SIM_SUBSET),--subset $(SIM_SUBSET),) \
		$(if $(SIM_MAX_CIRCUITS),--max-circuits $(SIM_MAX_CIRCUITS),) \
		$(if $(filter 0 false no,$(SIM_PROGRESS)),--no-progress,) \
		$(if $(SIM_PROGRESS_EVERY),--progress-every $(SIM_PROGRESS_EVERY),)

optimize-circuits: $(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB) $(OPTIMIZE_CIRCUITS_SCRIPT)
	$(PYTHON) $(OPTIMIZE_CIRCUITS_SCRIPT) \
		--output-root $(OPT_OUTPUT_ROOT) \
		--network-database $(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB) \
		--transistor-group $(OPT_TRANSISTOR_GROUP) \
		--population-size $(OPT_POPULATION_SIZE) \
		--offspring-size $(OPT_OFFSPRING_SIZE) \
		--generations $(OPT_GENERATIONS) \
		--f0 $(OPT_F0) \
		$(if $(OPT_RESUME_FROM),--resume-from $(OPT_RESUME_FROM),) \
		$(if $(filter 1 true yes,$(OPT_RESUME_IN_PLACE)),--resume-in-place,) \
		$(if $(filter 1 true yes,$(OPT_OVERWRITE_OUTPUT)),--overwrite-output,) \
		$(if $(OPT_AC_START),--ac-start $(OPT_AC_START),) \
		$(if $(OPT_AC_STOP),--ac-stop $(OPT_AC_STOP),) \
		--sim-threads $(OPT_SIM_THREADS) \
		$(if $(OPT_CIRCUIT_DATABASE),--circuit-database $(OPT_CIRCUIT_DATABASE),) \
		--vg-start 0.75 \
		--vg-stop 1.25 \
		--vg-step 0.005 \
		--reference-partitions $(OPT_PARTITIONS) \
		--crossover-probability $(OPT_CROSSOVER_PROB) \
		--mutation-probability $(OPT_MUTATION_PROB) \
		--gate-r-indexes 0 \
		--gate-l-indexes 1:3 \
		--gate-c-indexes 0 \
		--feedback-r-indexes 0 \
		--feedback-l-indexes 0 \
		--load-l-indexes 1:3 \
		--source-l-indexes 1:3 \
		$(if $(OPT_SIM_TIMEOUT),--sim-timeout $(OPT_SIM_TIMEOUT),) \
		$(if $(OPT_MAX_NF_DB),--max-nf-db $(OPT_MAX_NF_DB),) \
		$(if $(OPT_MAX_POWER_DBM),--max-power-dbm $(OPT_MAX_POWER_DBM),) \
		$(if $(OPT_MIN_S21_DB),--min-s21-db $(OPT_MIN_S21_DB),) \
		$(if $(OPT_MIN_F_BW),--min-f-bw $(OPT_MIN_F_BW),) \
		$(if $(OPT_MAX_S11_DB),--max-s11-db $(OPT_MAX_S11_DB),) \
		$(if $(OPT_SEED),--seed $(OPT_SEED),) \

optimize-circuits-demo: $(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB) $(OPTIMIZE_CIRCUITS_SCRIPT)
	$(PYTHON) $(OPTIMIZE_CIRCUITS_SCRIPT) \
		--output-root optimization_demo \
		--network-database $(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB) \
		--transistor-group $(OPT_TRANSISTOR_GROUP) \
		--population-size 12 \
		--offspring-size 12 \
		--generations 3 \
		--f0 $(OPT_F0) \
		$(if $(OPT_RESUME_FROM),--resume-from $(OPT_RESUME_FROM),) \
		$(if $(filter 1 true yes,$(OPT_RESUME_IN_PLACE)),--resume-in-place,) \
		$(if $(filter 1 true yes,$(OPT_OVERWRITE_OUTPUT)),--overwrite-output,) \
		$(if $(OPT_AC_START),--ac-start $(OPT_AC_START),) \
		$(if $(OPT_AC_STOP),--ac-stop $(OPT_AC_STOP),) \
		--sim-threads $(OPT_SIM_THREADS) \
		--sim-timeout $(OPT_DEMO_SIM_TIMEOUT) \
		$(if $(OPT_CIRCUIT_DATABASE),--circuit-database $(OPT_CIRCUIT_DATABASE),) \
		--vg-start 0.75 \
		--vg-stop 1.15 \
		--vg-step 0.025 \
		--reference-partitions $(OPT_PARTITIONS) \
		--crossover-probability $(OPT_CROSSOVER_PROB) \
		--mutation-probability $(OPT_MUTATION_PROB) \
		--gate-r-indexes 0 \
		--gate-l-indexes 1:3 \
		--gate-c-indexes 0 \
		--feedback-r-indexes 0 \
		--feedback-l-indexes 0 \
		--source-l-indexes 1:3 \
		--load-l-indexes 1:3 \
		$(if $(OPT_MAX_NF_DB),--max-nf-db $(OPT_MAX_NF_DB),) \
		$(if $(OPT_MAX_POWER_DBM),--max-power-dbm $(OPT_MAX_POWER_DBM),) \
		$(if $(OPT_MIN_S21_DB),--min-s21-db $(OPT_MIN_S21_DB),) \
		$(if $(OPT_MIN_F_BW),--min-f-bw $(OPT_MIN_F_BW),) \
		$(if $(OPT_MAX_S11_DB),--max-s11-db $(OPT_MAX_S11_DB),) \
		--seed 1 

optimize-circuits-mopso: $(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB) $(OPTIMIZE_CIRCUITS_MOPSO_SCRIPT)
	$(PYTHON) $(OPTIMIZE_CIRCUITS_MOPSO_SCRIPT) \
		--output-root $(MOPSO_OUTPUT_ROOT) \
		--network-database $(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB) \
		--transistor-group $(MOPSO_TRANSISTOR_GROUP) \
		--swarm-size $(MOPSO_SWARM_SIZE) \
		--iterations $(MOPSO_ITERATIONS) \
		--archive-size $(MOPSO_ARCHIVE_SIZE) \
		--f0 $(MOPSO_F0) \
		$(if $(filter 1 true yes,$(MOPSO_OVERWRITE_OUTPUT)),--overwrite-output,) \
		$(if $(MOPSO_AC_START),--ac-start $(MOPSO_AC_START),) \
		$(if $(MOPSO_AC_STOP),--ac-stop $(MOPSO_AC_STOP),) \
		--sim-threads $(MOPSO_SIM_THREADS) \
		$(if $(MOPSO_CIRCUIT_DATABASE),--circuit-database $(MOPSO_CIRCUIT_DATABASE),) \
		--vg-start 0.75 \
		--vg-stop 1.25 \
		--vg-step 0.005 \
		--archive-partitions $(MOPSO_ARCHIVE_PARTITIONS) \
		--inertia-weight $(MOPSO_INERTIA_WEIGHT) \
		--cognitive-weight $(MOPSO_COGNITIVE_WEIGHT) \
		--social-weight $(MOPSO_SOCIAL_WEIGHT) \
		--velocity-clamp $(MOPSO_VELOCITY_CLAMP) \
		--mutation-probability $(MOPSO_MUTATION_PROB) \
		--gate-r-indexes 0 \
		--gate-l-indexes 1:3 \
		--gate-c-indexes 0 \
		--feedback-r-indexes 0 \
		--feedback-l-indexes 0 \
		--load-l-indexes 1:3 \
		--source-l-indexes 1:3 \
		$(if $(MOPSO_SIM_TIMEOUT),--sim-timeout $(MOPSO_SIM_TIMEOUT),) \
		$(if $(MOPSO_MAX_NF_DB),--max-nf-db $(MOPSO_MAX_NF_DB),) \
		$(if $(MOPSO_MAX_POWER_DBM),--max-power-dbm $(MOPSO_MAX_POWER_DBM),) \
		$(if $(MOPSO_MIN_S21_DB),--min-s21-db $(MOPSO_MIN_S21_DB),) \
		$(if $(MOPSO_MIN_F_BW),--min-f-bw $(MOPSO_MIN_F_BW),) \
		$(if $(MOPSO_MAX_S11_DB),--max-s11-db $(MOPSO_MAX_S11_DB),) \
		$(if $(MOPSO_SEED),--seed $(MOPSO_SEED),)

optimize-circuits-mopso-demo: $(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB) $(OPTIMIZE_CIRCUITS_MOPSO_SCRIPT)
	$(PYTHON) $(OPTIMIZE_CIRCUITS_MOPSO_SCRIPT) \
		--output-root optimization_demo_mopso \
		--network-database $(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB) \
		--transistor-group $(MOPSO_TRANSISTOR_GROUP) \
		--swarm-size 12 \
		--iterations 3 \
		--archive-size 24 \
		--f0 $(MOPSO_F0) \
		$(if $(filter 1 true yes,$(MOPSO_OVERWRITE_OUTPUT)),--overwrite-output,) \
		$(if $(MOPSO_AC_START),--ac-start $(MOPSO_AC_START),) \
		$(if $(MOPSO_AC_STOP),--ac-stop $(MOPSO_AC_STOP),) \
		--sim-threads $(MOPSO_SIM_THREADS) \
		--sim-timeout $(MOPSO_DEMO_SIM_TIMEOUT) \
		$(if $(MOPSO_CIRCUIT_DATABASE),--circuit-database $(MOPSO_CIRCUIT_DATABASE),) \
		--vg-start 0.75 \
		--vg-stop 1.15 \
		--vg-step 0.025 \
		--archive-partitions $(MOPSO_ARCHIVE_PARTITIONS) \
		--inertia-weight $(MOPSO_INERTIA_WEIGHT) \
		--cognitive-weight $(MOPSO_COGNITIVE_WEIGHT) \
		--social-weight $(MOPSO_SOCIAL_WEIGHT) \
		--velocity-clamp $(MOPSO_VELOCITY_CLAMP) \
		--mutation-probability $(MOPSO_MUTATION_PROB) \
		--gate-r-indexes 0 \
		--gate-l-indexes 1:3 \
		--gate-c-indexes 0 \
		--feedback-r-indexes 0 \
		--feedback-l-indexes 0 \
		--source-l-indexes 1:3 \
		--load-l-indexes 1:3 \
		$(if $(MOPSO_MAX_NF_DB),--max-nf-db $(MOPSO_MAX_NF_DB),) \
		$(if $(MOPSO_MAX_POWER_DBM),--max-power-dbm $(MOPSO_MAX_POWER_DBM),) \
		$(if $(MOPSO_MIN_S21_DB),--min-s21-db $(MOPSO_MIN_S21_DB),) \
		$(if $(MOPSO_MIN_F_BW),--min-f-bw $(MOPSO_MIN_F_BW),) \
		$(if $(MOPSO_MAX_S11_DB),--max-s11-db $(MOPSO_MAX_S11_DB),) \
		--seed 1

build-circuit-database: $(CIRCUIT_DATABASE_SCRIPT)
	$(PYTHON) $(CIRCUIT_DATABASE_SCRIPT) \
		--output $(CIRCUIT_DATABASE_OUTPUT) \
		$(if $(filter 1 true yes,$(CIRCUIT_DATABASE_OVERWRITE)),--overwrite,) \
		$(if $(filter 1 true yes,$(CIRCUIT_DATABASE_SKIP_MISSING)),--skip-missing,) \
		$(CIRCUIT_DATABASE_RUNS)

append-circuit-database: build-circuit-database

rebuild-circuit-database:
	$(MAKE) build-circuit-database CIRCUIT_DATABASE_OVERWRITE=1

analysis-summary:
	$(ANALYSIS_PYTHON) analysis/summarize_optimization.py $(ANALYSIS_RUN_ROOT) --top-count $(ANALYSIS_TOP_COUNT) $(ANALYSIS_FILTER_ARGS)

analysis-export:
	$(ANALYSIS_PYTHON) analysis/summarize_optimization.py $(ANALYSIS_RUN_ROOT) --output-dir $(ANALYSIS_OUTPUT_DIR) --top-count $(ANALYSIS_TOP_COUNT) $(ANALYSIS_FILTER_ARGS)

analysis-plots:
	$(ANALYSIS_PLOT_PYTHON) analysis/plot_optimization.py $(ANALYSIS_RUN_ROOT) --output-dir $(ANALYSIS_PLOTS_DIR) --color-by $(ANALYSIS_COLOR_BY) $(ANALYSIS_FILTER_ARGS)

analysis-plots-history:
	$(ANALYSIS_PLOT_PYTHON) analysis/plot_optimization.py $(ANALYSIS_RUN_ROOT) --output-dir $(ANALYSIS_HISTORY_PLOTS_DIR) --color-by $(ANALYSIS_COLOR_BY) --record-scope all $(ANALYSIS_FILTER_ARGS)

analysis-pareto-evolution:
	$(ANALYSIS_PLOT_PYTHON) analysis/plot_pareto_evolution.py $(ANALYSIS_RUN_ROOT) \
		--output-dir $(ANALYSIS_PARETO_EVOLUTION_DIR) \
		--pairs $(ANALYSIS_PARETO_EVOLUTION_PAIRS) \
		--generation-step $(ANALYSIS_PARETO_EVOLUTION_EVERY) \
		--record-scope $(ANALYSIS_PARETO_EVOLUTION_SCOPE) \
		--generation-source $(ANALYSIS_PARETO_EVOLUTION_GENERATION_SOURCE) \
		$(if $(ANALYSIS_PARETO_EVOLUTION_GENERATIONS_DIR),--generations-dir $(ANALYSIS_PARETO_EVOLUTION_GENERATIONS_DIR),) \
		$(if $(ANALYSIS_PARETO_EVOLUTION_MAX_GENERATIONS),--max-generations $(ANALYSIS_PARETO_EVOLUTION_MAX_GENERATIONS),) \
		$(if $(filter 1 true yes,$(ANALYSIS_PARETO_EVOLUTION_INCLUDE_PARTIAL)),--include-partial,) \
		$(if $(filter 1 true yes,$(ANALYSIS_PARETO_EVOLUTION_HIDE_VALID)),--hide-valid-overlay,) \
		$(if $(filter 1 true yes,$(ANALYSIS_PARETO_EVOLUTION_HIDE_GENERATION_POPULATION)),--hide-generation-population,) \
		$(if $(filter 1 true yes,$(ANALYSIS_PARETO_EVOLUTION_FILTER_CONSTRAINTS)),--filter-constraints,) \
		$(if $(filter 1 true yes,$(ANALYSIS_PARETO_EVOLUTION_SHADE_CONSTRAINTS)),--shade-constraint-region,) \
		$(if $(filter 1 true yes,$(ANALYSIS_PARETO_EVOLUTION_SHADE_FRONTIER_REGION)),--shade-frontier-region,) \
		--frontier-region-alpha $(ANALYSIS_PARETO_EVOLUTION_FRONTIER_REGION_ALPHA) \
		$(ANALYSIS_FILTER_ARGS)

analysis-pareto-evolution-compare:
	$(ANALYSIS_PLOT_PYTHON) analysis/plot_pareto_evolution_compare.py $(ANALYSIS_PARETO_COMPARE_RUNS) \
		--output-dir $(ANALYSIS_PARETO_COMPARE_OUTPUT_DIR) \
		--pairs $(ANALYSIS_PARETO_COMPARE_PAIRS) \
		--generation-step $(ANALYSIS_PARETO_COMPARE_EVERY) \
		--record-scope $(ANALYSIS_PARETO_COMPARE_SCOPE) \
		--generation-mode $(ANALYSIS_PARETO_COMPARE_GENERATION_MODE) \
		--generation-source $(ANALYSIS_PARETO_COMPARE_GENERATION_SOURCE) \
		$(if $(ANALYSIS_PARETO_COMPARE_GENERATIONS_DIRS),--generations-dirs $(ANALYSIS_PARETO_COMPARE_GENERATIONS_DIRS),) \
		$(if $(ANALYSIS_PARETO_COMPARE_LABELS),--labels $(ANALYSIS_PARETO_COMPARE_LABELS),) \
		$(if $(ANALYSIS_PARETO_COMPARE_MAX_GENERATIONS),--max-generations $(ANALYSIS_PARETO_COMPARE_MAX_GENERATIONS),) \
		$(if $(filter 1 true yes,$(ANALYSIS_PARETO_COMPARE_INCLUDE_PARTIAL)),--include-partial,) \
		$(if $(filter 1 true yes,$(ANALYSIS_PARETO_COMPARE_HIDE_HISTORY)),--hide-history,) \
		$(if $(filter 1 true yes,$(ANALYSIS_PARETO_COMPARE_HIDE_VALID)),--hide-valid-overlay,) \
		$(if $(filter 1 true yes,$(ANALYSIS_PARETO_COMPARE_HIDE_GENERATION_POPULATION)),--hide-generation-population,) \
		$(if $(filter 1 true yes,$(ANALYSIS_PARETO_COMPARE_FILTER_CONSTRAINTS)),--filter-constraints,) \
		$(if $(filter 1 true yes,$(ANALYSIS_PARETO_COMPARE_SHADE_CONSTRAINTS)),--shade-constraint-region,) \
		$(if $(filter 1 true yes,$(ANALYSIS_PARETO_COMPARE_SHADE_FRONTIER_REGION)),--shade-frontier-region,) \
		--frontier-region-alpha $(ANALYSIS_PARETO_COMPARE_FRONTIER_REGION_ALPHA) \
		$(ANALYSIS_FILTER_ARGS)

analysis-pareto-animation:
	$(ANALYSIS_PLOT_PYTHON) analysis/animate_png_sequence.py $(ANALYSIS_ANIMATION_INPUT_DIR) \
		--output $(ANALYSIS_ANIMATION_OUTPUT) \
		--fps $(ANALYSIS_ANIMATION_FPS) \
		--engine $(ANALYSIS_ANIMATION_ENGINE) \
		--overwrite

analysis-performance:
	$(ANALYSIS_PYTHON) analysis/evaluate_optimization.py $(ANALYSIS_COMPARE_RUNS) --output-dir $(ANALYSIS_PERFORMANCE_OUTPUT_DIR) --record-scope $(ANALYSIS_PERFORMANCE_RECORD_SCOPE) --hv-samples $(ANALYSIS_HV_SAMPLES) --hv-seed $(ANALYSIS_HV_SEED) --gd-power $(ANALYSIS_GD_POWER) $(ANALYSIS_COMPARE_LABEL_ARGS) $(ANALYSIS_FILTER_ARGS)

analysis-plot-all:
	$(MAKE) analysis-plots ANALYSIS_COLOR_BY=wtot_um
	$(MAKE) analysis-plots ANALYSIS_COLOR_BY=gate_l
	$(MAKE) analysis-plots ANALYSIS_COLOR_BY=vg
	$(MAKE) analysis-plots ANALYSIS_COLOR_BY=length_um
	$(MAKE) analysis-plots ANALYSIS_COLOR_BY=feedback_c

analysis-plot-all-history:
	$(MAKE) analysis-plots-history ANALYSIS_COLOR_BY=wtot_um
	$(MAKE) analysis-plots-history ANALYSIS_COLOR_BY=gate_l
	$(MAKE) analysis-plots-history ANALYSIS_COLOR_BY=vg
	$(MAKE) analysis-plots-history ANALYSIS_COLOR_BY=length_um
	$(MAKE) analysis-plots-history ANALYSIS_COLOR_BY=feedback_c

analysis-all: analysis-export analysis-plot-all

clean-analysis:
	rm -rf $(ANALYSIS_CLEAN_PATHS)


clean-circuits:
	rm -rf $(CIRCUIT_OUTPUT_ROOT) 

clean-optimization:
	rm -rf $(OPT_OUTPUT_ROOT)
