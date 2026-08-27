#!/bin/bash

# SPDX-License-Identifier: BSD-3-Clause

echo "Running stomp on CGYRO"
echo "======================"

# Number of Makefile threads to use
N_THREADS=$(( $(nproc) / 6 ))
if [[ "$N_THREADS" == "0" ]]; then
  N_THREADS="1"
fi

echo "Making stomp outputs with '-j $N_THREADS'..."

# Generate stomp outputs
make -s -j $N_THREADS

# Check all outputs
OUT_FILES=$(ls src/*.out)
for FILE in $OUT_FILES; do
  EXP_FILE=expected/$(basename $FILE)
  if ! cmp -s $FILE $EXP_FILE; then
    echo -e "\e[31mFailed\e[0m: $FILE" \
            "doesn't match $EXP_FILE"
    exit -1
  fi
done

echo -e "\e[32mPassed\e[0m: all checks gave expected outputs!"
exit 0
