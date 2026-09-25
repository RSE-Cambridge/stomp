#!/bin/bash

# SPDX-License-Identifier: BSD-3-Clause

echo "Running application tests (UKCA)"
echo "================================"

URL="https://raw.githubusercontent.com/mn416/ukca"
URL="$URL/refs/heads/mn416-stomp/src/science/core/chemistry/"

mkdir -p src
(cd src && wget -q "$URL/ukca_chemistry_ctl_full_mod.F90")
(cd src && wget -q "$URL/asad/asad_mod.F90")
(cd src && wget -q "$URL/asad/asad_cdrive.F90")


stomp --threadsafe asad_cdrive \
      --small-check \
      --no-colour --no-progress \
      -l src/asad_cdrive.F90 \
      -l src/asad_mod.F90 \
      src/ukca_chemistry_ctl_full_mod.F90 > \
      src/ukca_chemistry_ctl_full_mod.out

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
