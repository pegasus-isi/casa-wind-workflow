#!/bin/bash

for i in {7..10}; do
    TOP_DIR=EDGE-CLOUD-RUN0$i
    for FILE in ../invoke_90sec/*.yml;
    do
        echo "CURRENT FILE: $FILE"
        pegasus-plan \
        -Dpegasus.catalog.replica.file=edge_cloud_rc \
        -Dpegasus.catalog.site.file=sites.yml \
        -Dpegasus.mode=development \
        -Dpegasus.integrity.checking=none \
        -Dpegasus.data.configuration=nonsharedfs \
        -Dpegasus.transfer.bypass.input.staging=True \
        -Dpegasus.monitord.encoding=json \
        -Dpegasus.catalog.workflow.amqp.url=amqp://friend:donatedata@msgs.pegasus.isi.edu:5672/prod/workflow \
        -Dpegasus.transfer.links=True \
        --dir $TOP_DIR \
        --output-sites=local \
        --sites=condorpool \
        --staging-site condorpool=staging \
        --force \
        --cluster label \
        $FILE
    done
    
    start=$(date +%s)
    for submit_dir in ./$TOP_DIR/panorama/pegasus/casa-wind/*
    do
        pegasus-run $submit_dir
    done
    
    while true; do
        if pegasus-status | grep -q "no matching jobs"; then
            break
        fi
        clear
        pegasus-status
        sleep 1
    done
    end=$(date +%s)

    echo "$((end-start))" > $TOP_DIR/duration.txt
done
