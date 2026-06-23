SHELL = /bin/bash

# DRB (dataracebench) source files and include files
DRB_FTN := dataracebench/micro-benchmarks-fortran/
DRB_SRC := $(wildcard $(DRB_FTN)/*.f95)
DRB_SRC += $(wildcard $(DRB_FTN)/*.F95)
DRB_INC := "-I dataracebench/micro-benchmarks-fortran/polybench"
DRB_INC += "-I dataracebench/micro-benchmarks-fortran/utilities"
DRB_OUT := $(patsubst $(DRB_FTN)/%.f95, drb-out/%.out, $(DRB_SRC))

.phony: top
top: run-drb run-ompoff

.phony: clean
clean:
	@rm -rf drb-out
	@rm -rf drb-results.txt
	@rm -rf OMPOff
	@rm -rf ompoff-results.txt

# Download DRB if not there
dataracebench/README.md:
	@git submodule update --init --recursive

# Create DRB output dir if not there
drb-out/:
	@mkdir drb-out

# Run stomp on DRB
drb-out/%.out: $(DRB_FTN)/%.f95
	@stomp $(DRB_INC) $< 2>/dev/null > $@
drb-out/%.out: $(DRB_FTN)/%.F95
	@stomp $(DRB_INC) $< 2>/dev/null > $@

# Generate DRB output files
.phony:
drb: dataracebench/README.md drb-out/ $(DRB_OUT)

.phony: run-drb
run-drb:
	@echo "Running stomp on dataracebench"
	@echo "=============================="
	@./run-drb.sh
	@echo

.phony: run-ompoff
run-ompoff:
	@echo "Running stomp on OMPOff"
	@echo "======================="
	@./run-ompoff.sh
	@echo
