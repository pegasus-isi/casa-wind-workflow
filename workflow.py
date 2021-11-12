#!/usr/bin/env python
import sys
import os
import pwd
import time
from Pegasus.api import *
from datetime import datetime
from argparse import ArgumentParser
from pathlib import Path

props = Properties()
props["pegasus.mode"] = "development"
props.write()

max_wind_filename = "max_wind.png"
pointalert_filename = "pointAlert_config.txt"
hospital_locations_filename = "hospital_locations.geojson"

class CASAWorkflow(object):
    def __init__(self, outdir, radar_files):
        self.outdir = outdir
        self.radar_files = radar_files
        self.rc = ReplicaCatalog()
        self.tc = TransformationCatalog()

    def generate_workflow(self):
        "Generate a workflow"
        ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
        workflow = Workflow("casa_wind_wf-%s" % ts)

        unzip = Transformation(
            "tar",
            site="condorpool",
            pfn="/bin/tar",
            is_stageable=False,
        )  
        
        um_vel = Transformation(
            "um_vel",
            site="local",
            pfn="",
            is_stageable=True
        )

        post_vel = Transformation(
            "post_vel",
            site="local",
            pfn="",
            is_stageable=True
        )

        mvt = Transformation(
            "mvt",
            site="local",
            pfn="",
            is_stageable=True
        )

        point_alert = Transformation(
            "point_alert",
            site="local",
            pfn="",
            is_stageable=True
        )


        max_wind_file = File(max_wind_filename)
        self.rc.add_replica("local", max_wind_file, Path("input/").resolve() / max_wind_filename)

        pointalert_file = File(pointalert_filename)
        self.rc.add_replica("local", pointalert_file, Path("input/").resolve() / pointalert_filename)

        hospital_locations_file = File(hospital_locations_filename)
        self.rc.add_replica("local", hospital_locations_file, Path("input/").resolve() / hospital_locations_filename)

        input_files = []
        output_files = []
        unzip_jobs = []

        for f in radar_files:
            p = Path(f)
            input_filename = p.name
            output_filename = p.stem
            extension = p.suffix

            if extension == "gz":
                input_files.append(f)
                radar_inputs.append(output_filename)
                rc.add_replica("local", File(input_filename), Path("input/").resolve() / input_filename)

                unzip_job = Job("tar").add_args("-xf", f, output_filename)\
                    .add_inputs(f)\
                    .add_outputs(output_filename)

                unzip_jobs.append(unzip_job)

            else:
                radar_inputs.append(output_filename)

        string_start = self.radar_files[-1].find("-")
        string_end = self.radar_files[-1].find(".", string_start)
        last_time = self.radar_files[-1][string_start+1:string_end]

        max_velocity = File("MaxVelocity_"+last_time+".netcdf")
        maxvel_job = Job(um_vel).add_args((" ".join(radar_inputs)))\
                            .add_inputs(*radar_inputs)\
                            .add_outputs(max_velocity)

        max_velocity_image = File(max_velocity.name[:-7]+".png")
        postvel_job = Job(post_vel).add_args(("-c", max_wind_file, "-q 235 -z 11.176,38", "-o", max_velocity_image, max_velocity))\
                            .add_inputs(max_wind_file, max_velocity)\
                            .add_outputs(max_velocity_image)


        mvt_geojson_file = File("mvt_"+max_velocity.name[:-7]+".geojson")
        mvt_geojson_job = Job(mvt).add_args(max_velocity)\
                            .add_inputs(max_velocity)\
                            .add_outputs(mvt_geojson_file)    

        alert_geojson_file = File("alert_"+last_time+".geojson")
        point_alert_job = Job(point_alert).add_args("-c", pointalert_file, "-p", "-o", alert_geojson_file, 
        "-g", hospital_locations_file, mvt_geojson_file)\
                            .add_inputs(pointalert_file, hospital_locations_file, mvt_geojson_file)\
                            .add_outputs(alert_geojson_file)   

        workflow.add_jobs(*unzip_jobs, maxvel_job, postvel_job, mvt_geojson_job, point_alert_job)
        workflow.add_transformation_catalog(tc)
        workflow.add_replica_catalog(rc) 

if __name__ == '__main__':
    parser = ArgumentParser(description="CASA Wind Workflow")
    parser.add_argument("-f", "--files", metavar="INPUT_FILES", type=str, nargs="+", help="Radar Files", required=True)
    parser.add_argument("-o", "--outdir", metavar="OUTPUT_LOCATION", type=str, help="DAX Directory", required=True)

    args = parser.parse_args()
    outdir = os.path.abspath(args.outdir)
    
    if not os.path.isdir(args.outdir):
        os.makedirs(outdir)

    workflow = CASAWorkflow(outdir, args.files)
    workflow.generate_workflow()
    workflow.plan(submit=True)
