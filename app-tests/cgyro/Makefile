#!/bin/bash

BASE_URL = https://raw.githubusercontent.com/mn416/gacode/
BRANCH_URL = $(BASE_URL)/refs/heads/mn416-stomp/cgyro/src/
USE_FILES = cgyro_globals.F90 \
            cgyro_field.F90 \
            cgyro_coll_data.F90
SRC_FILES = cgyro_step_collision.F90 \
            cgyro_rhs.F90 \
            cgyro_nl_comm.F90
OUT_FILES = $(patsubst %.F90,src/%.out,$(SRC_FILES))
FILES = $(USE_FILES) $(SRC_FILES)
STOMP_FLAGS = -D OMPGPU
STOMP_FLAGS += -e WildcardImportInSubroutine
STOMP_FLAGS += --no-colour --no-progress
STOMP_FLAGS += -l src/cgyro_coll_data.F90
STOMP_FLAGS += -l src/cgyro_field.F90
STOMP_FLAGS += -l src/cgyro_globals.F90
STOMP_FLAGS += --sweep-threads 6 --smt-timeout 10000

.PHONY: top
top: $(OUT_FILES)

src/%.out: src/%.F90 $(patsubst %.F90,src/%.F90,$(USE_FILES))
	@stomp $(STOMP_FLAGS) $< > $@

.PHONY: download
download: $(patsubst %.F90,src/%.F90,$(FILES))

src/:
	@mkdir -p src

src/%.F90: src/
	@(cd src && wget -q $(BRANCH_URL)/$(@F))

.PHONY: clean
clean:
	@rm -rf src
