#!/usr/bin/env python

import sys
import os
import pwd
import time
import shutil
from Pegasus.DAX3 import *
from datetime import datetime
from argparse import ArgumentParser

class CASAWorkflow(object):
    def __init__(self, outdir, radar_files, default_properties, default_replica):
        self.outdir = outdir
        self.radar_files = radar_files
        self.default_replica = default_replica
        self.default_properties = default_properties
        self.replica = {}

    def generate_dax(self):
        "Generate a workflow"
        ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
        dax = ADAG("casa_wind_wf-%s" % ts)
        dax.metadata("name", "CASA Wind")
        USER = pwd.getpwuid(os.getuid())[0]
        dax.metadata("creator", "%s@%s" % (USER, os.uname()[1]))
        dax.metadata("created", time.ctime())

        # unzip files if needed
        radar_inputs = []
        last_time = "0"
        for pfn in self.radar_files:
            if pfn.startswith("/") or pfn.startswith("file://"):
                site = "local"
            else:
                site = pfn.split("/")[2]
            lfn = pfn.split("/")[-1]
            self.replica[lfn] = {"site": site, "pfn": pfn}

            string_start = lfn.find("-")
            string_end = lfn.find(".", string_start)
            file_time = lfn[string_start+1:string_end]
            if file_time > last_time:
                last_time = file_time
            
            if lfn.endswith(".gz"):
                radar_input = lfn[:-3]
                radar_inputs.append([radar_input, file_time])

                unzip = Job("gunzip")
                unzip.addArguments(lfn)
                unzip.uses(lfn, link=Link.INPUT)
                unzip.uses(radar_input, link=Link.OUTPUT, transfer=False, register=False)
                dax.addJob(unzip)
            else:
                radar_inputs.append([lfn, file_time])

        #string_start = self.radar_files[-1].find("-")
        #string_start = self.radar_files[-1].find("-")
        #string_end = self.radar_files[-1].find(".", string_start)
        #last_time = self.radar_files[-1][string_start+1:string_end]

        radar_inputs.sort(key = lambda x: x[1])
        radar_inputs = [x[0] for x in radar_inputs]

        #calculate max velocity (maybe split them to multiple ones)
        max_velocity = File("MaxVelocity_"+last_time+".netcdf")
        vel_job = Job("um_vel")
        vel_job.addArguments(" ".join(radar_inputs))
        for radar_input in radar_inputs:
            vel_job.uses(radar_input, link=Link.INPUT)
        vel_job.uses(max_velocity, link=Link.OUTPUT, transfer=True, register=False)
        dax.addJob(vel_job)

        # generate image from max velocity
        colorscale = File("max_wind.png")
        max_velocity_image = File(max_velocity.name[:-7]+".png")
        post_vel_job = Job("merged_netcdf2png")
        post_vel_job.addArguments("-c", colorscale, "-q 235 -z 11.176,38", "-o", max_velocity_image, max_velocity)
        post_vel_job.uses(max_velocity, link=Link.INPUT)
        post_vel_job.uses(colorscale, link=Link.INPUT)
        post_vel_job.uses(max_velocity_image, link=Link.OUTPUT, transfer=True, register=False)
        dax.addJob(post_vel_job)

        # generate geojson file from max velocity
        mvt_geojson_file = File("mvt_"+max_velocity.name[:-7]+".geojson")
        mvt_job = Job("mvt")
        mvt_job.addArguments(max_velocity)
        mvt_job.uses(max_velocity, link=Link.INPUT)
        mvt_job.uses(mvt_geojson_file, link=Link.OUTPUT, transfer=True, register=False)
        dax.addJob(mvt_job)

        # generate alert geojson file from max velocity
        pointalert_config = File("pointAlert_config.txt")
        hospitals_geojson_file = File("hospital_locations.geojson")
        alert_geojson_file = File("alert_"+last_time+".geojson")
        pointalert_job = Job("pointalert")
        #pointalert_job.addArguments("-c", pointalert_config, "-e -p", "-o", alert_geojson_file, "-g", hospitals_geojson_file, mvt_geojson_file)
        pointalert_job.addArguments("-c", pointalert_config, "-p", "-o", alert_geojson_file, "-g", hospitals_geojson_file, mvt_geojson_file)
        pointalert_job.uses(pointalert_config, link=Link.INPUT)
        pointalert_job.uses(hospitals_geojson_file, link=Link.INPUT)
        pointalert_job.uses(mvt_geojson_file, link=Link.INPUT)
        pointalert_job.uses(alert_geojson_file, link=Link.OUTPUT, transfer=True, register=False)
        dax.addJob(pointalert_job)

        # Write the DAX file
        dax_file = os.path.join(self.outdir, dax.name+".dax")
        dax.writeXMLFile(dax_file)

        # Write replica catalog
        replica_file =  os.path.join(self.outdir, dax.name+".rc.txt")
        shutil.copy(self.default_replica, replica_file)
        with open(replica_file, 'a') as g:
            for lfn in self.replica:
                g.write("{0}    {1}    site=\"{2}\"\n".format(lfn, self.replica[lfn]["pfn"], self.replica[lfn]["site"]))
        
        
        properties_file =  os.path.join(self.outdir, dax.name+".properties")
        shutil.copy(self.default_properties, properties_file)
        with open(properties_file, 'a') as g:
            g.write("pegasus.catalog.replica.file={0}\n".format(replica_file))
        
        print "{0} {1}".format(dax_file,properties_file)

    def generate_workflow(self):
        # Generate dax
        self.generate_dax()

if __name__ == '__main__':
    parser = ArgumentParser(description="CASA Wind Workflow")
    parser.add_argument("-f", "--files", metavar="INPUT_FILES", type=str, nargs="+", help="Radar Files", required=True)
    parser.add_argument("-r", "--replica", metavar="DEFAULT_REPLICA", type=str, help="Default Replica Catalog", required=True)
    parser.add_argument("-p", "--properties", metavar="DEFAULT_PROPERTIES", type=str, help="Default Pegasus Properties", required=True)
    parser.add_argument("-o", "--outdir", metavar="OUTPUT_LOCATION", type=str, help="DAX Directory", required=True)

    args = parser.parse_args()
    outdir = os.path.abspath(args.outdir)
    
    if not os.path.isdir(args.outdir):
        os.makedirs(outdir)

    workflow = CASAWorkflow(outdir, args.files, args.properties, args.replica)
    workflow.generate_workflow()
