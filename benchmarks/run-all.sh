#!/bin/bash

# SPDX-License-Identifier: BSD-3-Clause

echo "Running stomp on DataRaceBench"
echo "=============================="
./run-drb.sh
echo

echo "Running stomp on OMPOff"
echo "======================="
./run-ompoff.sh
echo
