SHELL = /bin/bash

# DRB (dataracebench) source files and include files
DRB_FTN := dataracebench/micro-benchmarks-fortran/
DRB_SRC := $(wildcard $(DRB_FTN)/*.f95)
DRB_SRC += $(wildcard $(DRB_FTN)/*.F95)
DRB_INC := "-I dataracebench/micro-benchmarks-fortran/polybench"
DRB_INC += "-I dataracebench/micro-benchmarks-fortran/utilities"
DRB_OUT := $(patsubst $(DRB_FTN)/%.f95, drb-out/%.out, $(DRB_SRC))

# Issues to exclude because they are not strictly data races
DRB_EXCLUDE := -e ReadUninitialisedPrivate
DRB_EXCLUDE += -e UnsupportedArrayReduction
DRB_EXCLUDE += -e BadReductionClause

.phony: top
top:
	@echo "Type './run-all.sh' to run all tests."
	@echo "Type 'make clean' to tidy up."

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

.phony: prepare-drb
prepare-drb: dataracebench/ drb-out/

# Run stomp on DRB
drb-out/%.out: $(DRB_FTN)/%.f95
	@stomp $(DRB_EXCLUDE) $(DRB_INC) $< 2>/dev/null > $@
drb-out/%.out: $(DRB_FTN)/%.F95
	@stomp $(DRB_EXCLUDE) $(DRB_INC) $< 2>/dev/null > $@

# Make sure output directory and input files are ready before building
$(DRB_OUT): dataracebench/README.md | drb-out/

# Generate DRB output files
.phony:
drb: $(DRB_OUT)
