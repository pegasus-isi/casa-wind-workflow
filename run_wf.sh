#!/usr/bin/env bash

old_dir=`pwd`

cd $WIND_WORKFLOW_DIR

dax_name=$(python daxgen.py -o dax_outputs -f $@)
./plan.sh ${dax_name}

cd $old_dir
