#!/usr/bin/env bash

WIND_WORKFLOW_DIR=`pwd`
DAXFILES="$WIND_WORKFLOW_DIR/testcase_daxs_5min_window/*"

for DAXFILE in $DAXFILES; do
   echo "$(date) ---- Planning Daxfile: $DAXFILE"
   $WIND_WORKFLOW_DIR/plan.sh $DAXFILE
   
   sleep 300
done
