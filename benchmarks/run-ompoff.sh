#!/bin/bash

if [ ! -d OMPOff ]; then
  COMMIT="4e8950e"
  git clone git@github.com:rse-cambridge/OMPOff 2> /dev/null
  (cd OMPOff && git checkout $COMMIT 2> /dev/null)
  if [ $? -ne 0 ]; then
    echo "Did not have permission to clone" \
         "'git@github.com:rse-cambridge/OMPOff'"
    exit 0
  fi
fi

echo -n > ompoff-results.txt
FILES=$(ls OMPOff/src/OpenMP/*.F90)
for FILE in $FILES; do
  SHORT=$(basename $FILE .out)
  echo "# $SHORT" >> ompoff-results.txt
  stomp --no-progress \
        -I OMPOff/platforms/mn416-laptop/ \
        $FILE 2> /dev/null \
     >> ompoff-results.txt
  echo >> ompoff-results.txt
done

if cmp -s ompoff-results.txt expected/ompoff-results.txt; then
  echo -e "\e[32mPass\e[0m: 'ompoff-results.txt'" \
          "matches 'expected/ompoff-results.txt'"
else
  echo -e "\e[31mFail\e[0m: 'ompoff-results.txt'" \
          "doesn't match 'expected/ompoff-results.txt'"
fi
