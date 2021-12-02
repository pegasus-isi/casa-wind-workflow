#!/bin/bash

### EDGE ONLY RUNS ####################################### 
python3 generate-sc.py --edge-only

for i in {1..10}; do
    TOP_DIR=EDGE-RUN0$i
    for FILE in ../invoke_90sec/*.yml;
    do
        echo "CURRENT FILE: $FILE"
        pegasus-plan \
        -Dpegasus.catalog.replica.file=edge_rc \
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
        --cleanup none \
        --staging-site condorpool=condorpool \
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
        pegasus-status -l
        sleep 1
    done
    end=$(date +%s)

    echo "$((end-start))" > $TOP_DIR/duration.txt
done

### EDGE CLOUD RUNS ####################################### 
python3 generate-sc.py

for i in {1..10}; do
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
        --cleanup none \
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
        pegasus-status -l
        sleep 1
    done
    end=$(date +%s)

    echo "$((end-start))" > $TOP_DIR/duration.txt
done

### CLOUD RUNS ####################################### 
python3 generate-sc.py --cloud-only

for i in {1..10}; do
    TOP_DIR=CLOUD-RUN0$i

    for FILE in ../invoke_90sec/*.yml;
    do
        echo "CURRENT FILE: $FILE"
        pegasus-plan \
        -Dpegasus.catalog.replica.file=cloud_rc \
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
        --cleanup none \
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
        pegasus-status -l
        sleep 1
    done
    end=$(date +%s)

    echo "$((end-start))" > $TOP_DIR/duration.txt
done


