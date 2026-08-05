#!/bin/bash

# SPDX-License-Identifier: BSD-3-Clause

echo "Running stomp on all examples"
echo "============================="

# Number of Makefile threads to use
N_THREADS=$(( $(nproc) / 4 ))
if [[ "$N_THREADS" == "0" ]]; then
  N_THREADS="1"
fi

echo "Making stomp outputs with '-j $N_THREADS'..."

# Generate stomp outputs
make -s -j $N_THREADS gen

# Check all outputs
OUT_DIRS="out_f90 out_F90"
for OUT_DIR in $OUT_DIRS; do
  OUT_FILES=$(ls $OUT_DIR/*.out)
  for FILE in $OUT_FILES; do
    if ! cmp -s $FILE expected/$FILE; then
      echo -e "\e[31mFailed\e[0m: $FILE" \
              "doesn't match expected/$FILE"
      exit -1
    fi
  done
done

echo -e "\e[32mPassed\e[0m: all examples gave expected outputs!"
exit 0
