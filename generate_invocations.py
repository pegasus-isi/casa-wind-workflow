#!/usr/bin/env python3

import os
import glob
import time
import shutil
from datetime import datetime


input_dir = "input"

netcdf_files = glob.glob(os.path.join(input_dir, "*.netcdf.gz"))
netcdf_list = []

for f in netcdf_files:
    timestamp = f[f.find("-")+1:f.rfind(".netcdf")]
    timestamp = datetime.strptime(timestamp, "%Y%m%d-%H%M%S")
    netcdf_list.append((timestamp, f[f.find("/")+1:]))

netcdf_list = sorted(netcdf_list, key=lambda x: x[0], reverse=True)

f = netcdf_list.pop()
current_list = [f[1]]
i = 0
while netcdf_list:
    f_temp = netcdf_list.pop()
    t_delta = f_temp[0].timestamp() - f[0].timestamp()
    if t_delta < 90:
        current_list.append(f_temp[1])
    else:
        #print(len(current_list))
        last_timestamp = f_temp[1][f_temp[1].find("-")+1:f_temp[1].rfind(".netcdf")]
        #print("python3 workflow.py -o casa-wind-wf-{0}.yml -f {1}".format(last_timestamp, " ".join(current_list)))
        print("python3 workflow.py -o casa-wind-wf-{0}.yml -f {1}".format(i, " ".join(current_list)))
        f = f_temp
        current_list = [f[1]]
        i += 1

