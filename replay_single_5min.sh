#!/usr/bin/env bash

WIND_WORKFLOW_DIR=`pwd`
DAXFILES="$WIND_WORKFLOW_DIR/testcase_daxs_5min_window/*"

for DAXFILE in $DAXFILES; do
   echo "$(date) ---- Planning Daxfile: $DAXFILE"
   $WIND_WORKFLOW_DIR/plan.sh $DAXFILE
   
   while [[ "$(pegasus-status | head -n 1)" != "(no matching jobs found in Condor Q)" ]]; do
      sleep 300
   done
done
