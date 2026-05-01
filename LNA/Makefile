PYTHON ?= python3

PASSIVE_NETWORK_SCRIPT := src/scripts/passive_networks.py
PASSIVE_NETWORK_MULTI_OBJECTIVE_DB := src/database/passive_networks_mim_no_varactors.json
MIM_MODELS ?= sky130_fd_pr__cap_mim_m3_2
MIM_SIZES ?= 2x2 4x4 6x6 8x8 10x10
MIM_MF_VALUES ?= 1
POLY_RESISTOR_SELECTION ?= all
PASSIVE_NETWORK_TOPOLOGY ?= rlc-parallel
PASSIVE_MAX_RESISTORS_PER_NETWORK ?=
GENERATE_CIRCUITS_SCRIPT := src/scripts/generate_circuits.py
SIMULATE_CIRCUITS_SCRIPT := src/scripts/simulate_circuits.py
MAP_CIRCUITS_SCRIPT := src/scripts/map_circuits.py
CIRCUIT_OUTPUT_ROOT ?= generated_circuits
CIRCUIT_MAP_OUTPUT ?= $(CIRCUIT_OUTPUT_ROOT)/circuit_map.json
TRANSISTOR_GROUP ?= nmos_and_lvt
VG_START ?= 0.7
VG_STOP ?= 1.3
VG_STEP ?= 0.1
MAX_CIRCUITS ?=
PRINT_USEFUL_DATA ?= 1
SIM_THREADS ?= 8
SIM_PRIORITY ?= high
SIM_MAX_CIRCUITS ?=
SIM_SUBSET ?=
SIM_PROGRESS ?= 1
SIM_PROGRESS_EVERY ?= 1
MAP_MAX_CIRCUITS ?=
MAP_SUBSET ?=
MAP_UPDATE_METADATA ?= 0
MAP_PROGRESS ?= 1
MAP_PROGRESS_EVERY ?= 1000

.PHONY: all generate-passive-network-multiobjective clean-passive-network-multiobjective generate-circuits simulate-circuits analyze-circuits map-circuits generate-and-simulate-circuits clean-circuits

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

generate-circuits: $(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB) $(GENERATE_CIRCUITS_SCRIPT)
	$(PYTHON) $(GENERATE_CIRCUITS_SCRIPT) \
		--output-root $(CIRCUIT_OUTPUT_ROOT) \
		--network-database $(PASSIVE_NETWORK_MULTI_OBJECTIVE_DB) \
		--transistor-group $(TRANSISTOR_GROUP) \
		--vg-start $(VG_START) \
		--vg-stop $(VG_STOP) \
		--vg-step $(VG_STEP) \
		$(if $(filter 1 true yes,$(PRINT_USEFUL_DATA)),--print-useful-data,) \
		$(if $(MAX_CIRCUITS),--max-circuits $(MAX_CIRCUITS),)

simulate-circuits: $(SIMULATE_CIRCUITS_SCRIPT)
	$(PYTHON) $(SIMULATE_CIRCUITS_SCRIPT) \
		$(CIRCUIT_OUTPUT_ROOT) \
		--threads $(SIM_THREADS) \
		--priority $(SIM_PRIORITY) \
		$(if $(SIM_SUBSET),--subset $(SIM_SUBSET),) \
		$(if $(SIM_MAX_CIRCUITS),--max-circuits $(SIM_MAX_CIRCUITS),) \
		$(if $(filter 0 false no,$(SIM_PROGRESS)),--no-progress,) \
		$(if $(SIM_PROGRESS_EVERY),--progress-every $(SIM_PROGRESS_EVERY),)

analyze-circuits: $(SIMULATE_CIRCUITS_SCRIPT)
	$(PYTHON) $(SIMULATE_CIRCUITS_SCRIPT) \
		$(CIRCUIT_OUTPUT_ROOT) \
		--analyze-only \
		$(if $(SIM_SUBSET),--subset $(SIM_SUBSET),) \
		$(if $(SIM_MAX_CIRCUITS),--max-circuits $(SIM_MAX_CIRCUITS),) \
		$(if $(filter 0 false no,$(SIM_PROGRESS)),--no-progress,) \
		$(if $(SIM_PROGRESS_EVERY),--progress-every $(SIM_PROGRESS_EVERY),)

map-circuits: $(MAP_CIRCUITS_SCRIPT)
	$(PYTHON) $(MAP_CIRCUITS_SCRIPT) \
		$(CIRCUIT_OUTPUT_ROOT) \
		--output $(CIRCUIT_MAP_OUTPUT) \
		$(if $(MAP_SUBSET),--subset $(MAP_SUBSET),) \
		$(if $(MAP_MAX_CIRCUITS),--max-circuits $(MAP_MAX_CIRCUITS),) \
		$(if $(filter 1 true yes,$(MAP_UPDATE_METADATA)),--update-metadata,) \
		$(if $(filter 0 false no,$(MAP_PROGRESS)),--no-progress,) \
		$(if $(MAP_PROGRESS_EVERY),--progress-every $(MAP_PROGRESS_EVERY),)

generate-and-simulate-circuits: generate-circuits simulate-circuits

clean-circuits:
	rm -rf $(CIRCUIT_OUTPUT_ROOT)
