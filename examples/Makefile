# SPDX-License-Identifier: BSD-3-Clause

SHELL = /bin/bash

# Output files
OUT_f90 := $(patsubst %.f90, out_f90/%.out, $(wildcard *.f90))
OUT_F90 := $(patsubst %.F90, out_F90/%.out, $(wildcard *.F90))

# Disable progress/colour output from stomp
FLAGS += --no-progress
FLAGS += --no-colour

.phony: top
top:
	@echo "Type './run-all.sh' to run all examples."
	@echo "Type 'make clean' to tidy up."

.phony: clean
clean:
	@rm -rf out_f90 out_F90

# Create output dir if not there
out_f90/:
	@mkdir out_f90
out_F90/:
	@mkdir out_F90

# Generate outputs
out_f90/%.out: %.f90
	@stomp $(FLAGS) $(INC) $< 2>/dev/null > $@
out_F90/%.out: %.F90
	@stomp $(FLAGS) $(INC) $< 2>/dev/null > $@

# Make sure output directories are ready before building
$(OUT_f90): out_f90/
$(OUT_F90): out_F90/

# Generate output files
.phony: gen
gen: $(OUT_f90) $(OUT_F90)
