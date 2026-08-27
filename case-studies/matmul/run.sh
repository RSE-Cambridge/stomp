#!/bin/bash

# SPDX-License-Identifier: BSD-3-Clause

echo "MatMul case study"
echo "================="

# Generate stomp outputs
make -s

# Check all outputs
OUT_FILES=$(ls *.out)
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
