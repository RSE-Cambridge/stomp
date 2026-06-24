#!/bin/bash

# Number of Makefile threads to use
N_THREADS=$(( $(nproc) / 4 ))
if [[ "$N_THREADS" == "0" ]]; then
  N_THREADS="1"
fi

echo "Making stomp outputs with '-j $N_THREADS'..."

# Run stomp on DRB benhmarks
make -s -j $N_THREADS drb

# Get list of all outputs
ALL=$(ls drb-out/*.out)

echo -n > drb-results.txt
for B in $ALL; do
  OUTPUT=$(cat $B)
  SHORT_B=$(basename $B .out)
  if [[ $OUTPUT == *"All done."* ]]; then
    if [[ $OUTPUT == *"found 0 issues."* ]]; then
      if [[ $SHORT_B == *"-yes"* ]]; then
        RESULT="\e[33mFN\e[0m" 
      else
        RESULT="\e[32mTN\e[0m"
      fi
    else
      if [[ $SHORT_B == *"-yes"* ]]; then
        RESULT="\e[32mTP\e[0m"
      else
        RESULT="\e[33mFP\e[0m"
      fi
    fi
  else
    RESULT="\e[31mFAIL\e[0m"
  fi
  echo -e "$SHORT_B: $RESULT" >> drb-results.txt
done

echo "Generated 'drb-results.txt'"

N_FAIL=$(cat drb-results.txt | cut -d':' -f2| grep FAIL | wc -l)
N_TP=$(cat drb-results.txt | cut -d':' -f2| grep TP | wc -l)
N_TN=$(cat drb-results.txt | cut -d':' -f2| grep TN | wc -l)
N_FP=$(cat drb-results.txt | cut -d':' -f2| grep FP | wc -l)
N_FN=$(cat drb-results.txt | cut -d':' -f2| grep FN | wc -l)

echo -e "TP: $N_TP"
echo -e "TN: $N_TN"
echo -e "FP: $N_FP"
echo -e "FN: $N_FN"
echo -e "\e[32mRight\e[0m:" $(($N_TP + $N_TN))
echo -e "\e[33mWrong\e[0m:" $(($N_FP + $N_FN))

if cmp -s drb-results.txt expected/drb-results.txt; then
  echo -e "\e[32mPass\e[0m: 'drb-results.txt'" \
          "matches 'expected/drb-results.txt'"
else
  echo -e "\e[31mFail\e[0m: 'drb-results.txt'" \
          "doesn't match 'expected/drb-results.txt'"
fi
