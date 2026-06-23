#!/bin/bash

if [ ! -d OMPOff ]; then
  git clone git@github.com:rse-cambridge/OMPOff 2> /dev/null
  if [ $? -ne 0 ]; then
    echo "Did not have permission to clone" \
         "'git@github.com:rse-cambridge/OMPOff'"
    exit 0
  fi
fi

FILES=$(ls OMPOff/src/OpenMP/*.F90)
for FILE in $FILES; do
  SHORT=$(basename $FILE .out)
  echo -n "$SHORT: "
  OUTPUT=$(stomp -I OMPOff/platforms/mn416-laptop/ $FILE 2> /dev/null)
  # All benchmarks are expected to have no issues
  if [[ $OUTPUT == *"found 0 issues."* ]]; then
    RESULT="\e[32mpassed\e[0m"
  else
    RESULT="\e[31mfailed\e[0m"
  fi
  echo -e "$RESULT"
done
