#!/bin/bash

for d in EDGE-RUN0*/panorama/pegasus/casa-wind/*;
do
    pegasus-statistics $d
    rm $d/pegasus-worker-5.0.1-x86_64_ubuntu_18.tar.gz
done

