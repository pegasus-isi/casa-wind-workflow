#!/usr/bin env python3
from pathlib import Path 
from Pegasus.api import *

# edge: file url for all files
# cloud: http for gz files, http staging for other
# edge-cloud: file url for gz files, http url for other

edge_rc = ReplicaCatalog()
cloud_rc = ReplicaCatalog() 
edge_cloud_rc =  ReplicaCatalog()

edge_http_prefix = "http://10.100.100.192/~panorama/casa-data/{}"
edge_file_prefix = "/home/panorama/public_html/casa-data/{}"

staging_http_prefix = "http://10.100.101.107/~panorama/casa-data/{}"

for f in Path("input").iterdir():
    if f.name.endswith(".gz"):
        edge_rc.add_replica(site="condorpool", lfn=f.name, pfn=edge_file_prefix.format(f.name))
        edge_cloud_rc.add_replica(site="condorpool", lfn=f.name, pfn=edge_file_prefix.format(f.name))
        cloud_rc.add_replica(site="condorpool", lfn=f.name, pfn=edge_http_prefix.format(f.name))
    else:
        edge_rc.add_replica(site="condorpool", lfn=f.name, pfn=edge_file_prefix.format(f.name))
        edge_cloud_rc.add_replica(site="condorpool", lfn=f.name, pfn=staging_http_prefix.format(f.name))
        cloud_rc.add_replica(site="condorpool", lfn=f.name, pfn=staging_http_prefix.format(f.name))


edge_rc.write("edge_rc")
edge_cloud_rc.write("edge_cloud_rc")
cloud_rc.write("cloud_rc")

