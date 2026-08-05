# SPDX-License-Identifier: BSD-3-Clause

SHELL = /bin/bash

# DRB (dataracebench) source files and include files
DRB_FTN := dataracebench/micro-benchmarks-fortran/
DRB_SRC := $(wildcard $(DRB_FTN)/*.f95)
DRB_SRC += $(wildcard $(DRB_FTN)/*.F95)
DRB_INC := "-I dataracebench/micro-benchmarks-fortran/polybench"
DRB_INC += "-I dataracebench/micro-benchmarks-fortran/utilities"
DRB_OUT := $(patsubst $(DRB_FTN)/%.f95, drb-out/%.out, $(DRB_SRC))

# Issues to exclude because they are not strictly data races
DRB_FLAGS := -e ReadUninitialisedPrivate
DRB_FLAGS += -e UnsupportedArrayReduction
DRB_FLAGS += -e BadReductionClause
DRB_FLAGS += -e ImpureParallelCall
DRB_FLAGS += -e WildcardImportInSubroutine
DRB_FLAGS += -e UnsupportedTaskDirective
DRB_FLAGS += -e PSyIRLimitation

# Disable progress/colour output from stomp
DRB_FLAGS += --no-progress
DRB_FLAGS += --no-colour

.phony: top
top:
	@echo "Type './run-drb.sh' to run DataRaceBench benchmarks."
	@echo "Type 'make clean' to tidy up."

.phony: clean
clean:
	@rm -rf drb-out
	@rm -rf drb-results.txt

# Download DRB if not there
dataracebench/README.md:
	@git submodule update --init --recursive

# Create DRB output dir if not there
drb-out/:
	@mkdir drb-out

.phony: prepare-drb
prepare-drb: dataracebench/ drb-out/

# Run stomp on DRB
drb-out/%.out: $(DRB_FTN)/%.f95
	@stomp $(DRB_FLAGS) $(DRB_INC) $< 2>/dev/null > $@
drb-out/%.out: $(DRB_FTN)/%.F95
	@stomp $(DRB_FLAGS) $(DRB_INC) $< 2>/dev/null > $@

# Make sure output directory and input files are ready before building
$(DRB_OUT): dataracebench/README.md | drb-out/

# Generate DRB output files
.phony:
drb: $(DRB_OUT)
