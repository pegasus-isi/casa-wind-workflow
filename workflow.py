#!/usr/bin/env python3

import logging
import sys
import os
import pwd
import time
from Pegasus.api import *
from datetime import datetime
from argparse import ArgumentParser
from pathlib import Path
from typing import List

logging.basicConfig(level=logging.INFO)

props = Properties()
props["pegasus.mode"] = "development"
props.write()

max_wind_filename = "max_wind.png"
pointalert_filename = "pointAlert_config.txt"
hospital_locations_filename = "hospital_locations.geojson"

class CASAWorkflow(object):
    def __init__(self, outdir: str, radar_files: List[str]):
        self.outdir = outdir
        self.radar_files = radar_files
        
    def generate_tc(self) -> None:
        # generate transformation catalog and then return tc object
        # wf.add_transformation_catalog(generate_tc())
        tc = TransformationCatalog()

        unzip = Transformation(
            "unzip",
            site="condorpool",
            pfn="/bin/gunzip",
            is_stageable=False,
        )  

        casa_wind_cont = Container(
            "casa_wind_cont",
            Container.DOCKER,
            "docker:///pegasus/casa-wind"
        )
        
        um_vel = Transformation(
            "um_vel",
            site="condorpool",
            pfn="opt/UM_VEL/UM_VEL",
            is_stageable=False,
            container=casa_wind_cont
        )   

        post_vel = Transformation(
            "post_vel",
            site="condorpool",
            pfn="/opt/netcdf2png/merged_netcdf2png",
            is_stageable=False,
            container=casa_wind_cont
        )

        mvt = Transformation(
            "mvt",
            site="condorpool",
            pfn="/opt/mvt/mvt",
            is_stageable=False,
            container=casa_wind_cont
        )

        point_alert = Transformation(
            "point_alert",
            site="condorpool",
            pfn="/opt/pointAlert/pointAlert",
            is_stageable=False,
            container = casa_wind_cont
        )

        tc.add_transformations(unzip)
        tc.add_containers(casa_wind_cont)
        tc.add_transformations(um_vel)
        tc.add_transformations(post_vel)
        tc.add_transformations(mvt)
        tc.add_transformations(point_alert)

       	return tc 

    def generate_rc(self, files: List[str]) -> ReplicaCatalog:
        # generate replica catalog and then return rc object
        # wf.add_replica_catalog(generate_rc())
        rc = ReplicaCatalog()

        for f in files:
            p = Path(f)
            input_filename = p.name
            rc.add_replica("local", input_filename, Path("input/").resolve() / input_filename)
            
        rc.add_replica("local", max_wind_filename, Path("input/").resolve() / max_wind_filename)
        rc.add_replica("local", hospital_locations_filename, Path("input/").resolve() / hospital_locations_filename)
        rc.add_replica("local", pointalert_filename, Path("input/").resolve() / pointalert_filename)
        return rc

    def generate_workflow(self) -> Workflow:
        "Generate a workflow"
        ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
        workflow = Workflow("casa_wind_wf-%s" % ts)

        tc = self.generate_tc()

        rc = self.generate_rc(self.radar_files)
        unzip_jobs = []
        radar_inputs = []
        
        for lfn, pfn in rc.entries.items():
            lfn_name = lfn[0]
            if lfn_name.endswith(".gz"):
                output_filename = lfn_name[:-3]
                radar_inputs.append(output_filename)
                unzip_job = Job("unzip").add_args(lfn_name)\
                .add_inputs(lfn_name)\
                .add_outputs(output_filename)

                unzip_jobs.append(unzip_job)
                
            elif lfn_name.endswith(".netcdf"):
                radar_inputs.append(lfn_name)
        
        # note: j.add_inputs("a", "b", File("c"))
    
        string_start = self.radar_files[-1].find("-")
        string_end = self.radar_files[-1].find(".", string_start)
        last_time = self.radar_files[-1][string_start+1:string_end]

        max_velocity_name = "MaxVelocity_" + last_time
        max_velocity = File("MaxVelocity_"+last_time+".netcdf")
        maxvel_job = Job("um_vel").add_args((" ".join(radar_inputs)))\
                            .add_inputs(*radar_inputs)\
                            .add_outputs(max_velocity)

        max_velocity_image = File(max_velocity_name+".png")
        postvel_job = Job("post_vel").add_args("-c", max_wind_filename, "-q 235 -z 11.176,38", "-o", max_velocity_image, max_velocity)\
                            .add_inputs(max_wind_filename, max_velocity)\
                            .add_outputs(max_velocity_image)


        mvt_geojson_file = File("mvt_"+max_velocity_name+".geojson")
        mvt_geojson_job = Job("mvt").add_args(max_velocity)\
                            .add_inputs(max_velocity)\
                            .add_outputs(mvt_geojson_file)    

        alert_geojson_file = File("alert_"+last_time+".geojson")
        point_alert_job = Job("point_alert").add_args("-c", pointalert_filename, "-p", "-o", alert_geojson_file, 
        "-g", hospital_locations_filename, mvt_geojson_file)\
                            .add_inputs(pointalert_filename, hospital_locations_filename, mvt_geojson_file)\
                            .add_outputs(alert_geojson_file)   

        workflow.add_jobs(*unzip_jobs, maxvel_job, postvel_job, mvt_geojson_job, point_alert_job)
        workflow.add_transformation_catalog(tc)
        workflow.add_replica_catalog(rc) 
        
        return workflow

if __name__ == '__main__':
    parser = ArgumentParser(description="CASA Wind Workflow")
    parser.add_argument("-f", "--files", metavar="INPUT_FILES", type=str, nargs="+", help="Radar Files", required=True)
    parser.add_argument("-o", "--outdir", metavar="OUTPUT_LOCATION", type=str, help="DAX Directory", required=True)

    args = parser.parse_args()
    outdir = os.path.abspath(args.outdir)
    
    if not os.path.isdir(args.outdir):
        os.makedirs(outdir)

    casa_wf = CASAWorkflow(outdir, args.files)
    workflow = casa_wf.generate_workflow()
    workflow.write()
    workflow.graph(output="workflow.png", include_files=True, no_simplify=True, label="xform-id")
    workflow.plan(submit=True)
    workflow.wait()