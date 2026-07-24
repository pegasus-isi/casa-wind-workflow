#!/usr/bin/env python3
"""CASA Wind workflow generator (Pegasus 5).

Generates workflow.yml with the site, transformation, and replica catalogs
embedded, so it plans with a plain `pegasus-plan -s condorpool -o local
workflow.yml` — no external sites.xml/tc.txt/rc.txt and no --input-dir.

Given a window of radar sweep files (addison.tx-YYYYMMDD-HHMMSS.netcdf.gz):
  1. gunzip decompresses each sweep (host tool, no container)
  2. um_vel computes the max wind velocity over the window
  3. merged_netcdf2png renders the velocity field to a PNG
  4. mvt vectorizes the velocity field to GeoJSON
  5. pointalert intersects it with hospital locations into an alert GeoJSON
"""

import os
from argparse import ArgumentParser
from datetime import datetime, timezone

from Pegasus.api import (
    OS,
    Arch,
    Container,
    Directory,
    File,
    FileServer,
    Job,
    Operation,
    ReplicaCatalog,
    Site,
    SiteCatalog,
    Transformation,
    TransformationCatalog,
    Workflow,
)

AUX_INPUTS = ("max_wind.png", "pointAlert_config.txt", "hospital_locations.geojson")


class CASAWorkflow(object):
    def __init__(self, outdir, radar_files):
        self.outdir = outdir
        self.radar_files = radar_files

    def build_site_catalog(self):
        sc = SiteCatalog()

        base = os.getcwd()
        local = Site("local", arch=Arch.X86_64, os_type=OS.LINUX)
        local.add_directories(
            Directory(
                Directory.SHARED_SCRATCH, os.path.join(base, "scratch")
            ).add_file_servers(
                FileServer("file://" + os.path.join(base, "scratch"), Operation.ALL)
            ),
            Directory(
                Directory.SHARED_STORAGE, os.path.join(base, "output")
            ).add_file_servers(
                FileServer("file://" + os.path.join(base, "output"), Operation.ALL)
            ),
        )

        condorpool = Site("condorpool", arch=Arch.X86_64, os_type=OS.LINUX)
        condorpool.add_condor_profile(universe="vanilla")
        condorpool.add_pegasus_profile(style="condor", data_configuration="condorio")

        sc.add_sites(local, condorpool)
        return sc

    def build_transformation_catalog(self):
        tc = TransformationCatalog()

        # Singularity (not Docker): it pulls docker:// images straight from
        # the registry without a Docker daemon, so the workflow also runs on
        # hosts with only singularity/apptainer installed (e.g. Kubernetes
        # pods, HPC nodes).
        wind_container = Container(
            "wind_image",
            Container.SINGULARITY,
            image="docker://pegasus/casa-wind",
            image_site="docker_hub",
        )
        tc.add_containers(wind_container)

        # gunzip runs on the execute host directly — no container needed.
        tc.add_transformations(
            Transformation(
                "gunzip",
                site="condorpool",
                pfn="/bin/gunzip",
                is_stageable=False,
                arch=Arch.X86_64,
                os_type=OS.LINUX,
            )
        )
        for name, pfn in (
            ("um_vel", "/opt/UM_VEL/UM_VEL"),
            ("merged_netcdf2png", "/opt/netcdf2png/merged_netcdf2png"),
            ("mvt", "/opt/mvt/mvt"),
            ("pointalert", "/opt/pointAlert/pointAlert"),
        ):
            tc.add_transformations(
                Transformation(
                    name,
                    site="condorpool",
                    pfn=pfn,
                    is_stageable=False,
                    container=wind_container,
                    arch=Arch.X86_64,
                    os_type=OS.LINUX,
                )
            )
        return tc

    def build_replica_catalog(self):
        rc = ReplicaCatalog()
        input_dir = os.path.abspath("input")
        for aux in AUX_INPUTS:
            rc.add_replica("local", aux, "file://" + os.path.join(input_dir, aux))
        for path in self.radar_files:
            rc.add_replica("local", os.path.basename(path), "file://" + path)
        return rc

    def generate_workflow(self):
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        wf = Workflow("casa-wind-wf-%s" % ts)
        wf.add_metadata(name="CASA Wind")

        wf.add_site_catalog(self.build_site_catalog())
        wf.add_transformation_catalog(self.build_transformation_catalog())
        wf.add_replica_catalog(self.build_replica_catalog())

        # gunzip any compressed sweeps; the decompressed files are
        # intermediates consumed by um_vel (dependencies are inferred from
        # file usage).
        radar_inputs = []
        for path in self.radar_files:
            fn = os.path.basename(path)
            if fn.endswith(".gz"):
                unzipped = File(fn[:-3])
                radar_inputs.append(unzipped)
                unzip_job = Job("gunzip")
                unzip_job.add_args("--force", fn)
                unzip_job.add_inputs(File(fn))
                unzip_job.add_outputs(
                    unzipped, stage_out=False, register_replica=False
                )
                wf.add_jobs(unzip_job)
            else:
                radar_inputs.append(File(fn))

        # The window timestamp comes from the last sweep's filename
        # (between the first '-' and the following '.'), and names every
        # downstream product, e.g. addison.tx-20170329-071403.netcdf.gz
        # -> 20170329-071403.
        last_fn = os.path.basename(self.radar_files[-1])
        string_start = last_fn.find("-")
        string_end = last_fn.find(".", string_start)
        if string_start < 0 or string_end < 0:
            raise SystemExit(
                f"error: cannot find a -YYYYMMDD-HHMMSS. timestamp in "
                f"'{last_fn}' (expected e.g. addison.tx-20170329-071008.netcdf.gz)"
            )
        last_time = last_fn[string_start + 1 : string_end]

        # max wind velocity over the window
        max_velocity = File(f"MaxVelocity_{last_time}.netcdf")
        vel_job = Job("um_vel")
        vel_job.add_args(*radar_inputs)
        vel_job.add_inputs(*radar_inputs)
        vel_job.add_outputs(max_velocity, stage_out=True, register_replica=False)
        wf.add_jobs(vel_job)

        # velocity field -> PNG
        colorscale = File("max_wind.png")
        max_velocity_image = File(f"MaxVelocity_{last_time}.png")
        post_vel_job = Job("merged_netcdf2png")
        post_vel_job.add_args(
            "-c", colorscale, "-q 235 -z 11.176,38",
            "-o", max_velocity_image, max_velocity,
        )
        post_vel_job.add_inputs(colorscale, max_velocity)
        post_vel_job.add_outputs(
            max_velocity_image, stage_out=True, register_replica=False
        )
        wf.add_jobs(post_vel_job)

        # velocity field -> GeoJSON
        mvt_geojson_file = File(f"mvt_MaxVelocity_{last_time}.geojson")
        mvt_job = Job("mvt")
        mvt_job.add_args(max_velocity)
        mvt_job.add_inputs(max_velocity)
        mvt_job.add_outputs(
            mvt_geojson_file, stage_out=True, register_replica=False
        )
        wf.add_jobs(mvt_job)

        # alert GeoJSON for hospital locations inside the wind field
        pointalert_config = File("pointAlert_config.txt")
        hospitals_geojson_file = File("hospital_locations.geojson")
        alert_geojson_file = File(f"alert_{last_time}.geojson")
        pointalert_job = Job("pointalert")
        pointalert_job.add_args(
            "-c", pointalert_config, "-p", "-o", alert_geojson_file,
            "-g", hospitals_geojson_file, mvt_geojson_file,
        )
        pointalert_job.add_inputs(
            pointalert_config, hospitals_geojson_file, mvt_geojson_file
        )
        pointalert_job.add_outputs(
            alert_geojson_file, stage_out=True, register_replica=False
        )
        wf.add_jobs(pointalert_job)

        wf_path = os.path.join(self.outdir, "workflow.yml")
        wf.write(wf_path)
        print(wf_path)


def resolve_radar_file(name):
    """Absolute path of a radar file given bare name or path."""
    if os.path.isfile(name):
        return os.path.abspath(name)
    candidate = os.path.join("input", os.path.basename(name))
    if os.path.isfile(candidate):
        return os.path.abspath(candidate)
    raise SystemExit(f"error: radar file '{name}' not found (looked in ./input/)")


if __name__ == "__main__":
    parser = ArgumentParser(description="CASA Wind Workflow")
    parser.add_argument(
        "-f",
        "--files",
        metavar="INPUT_FILE",
        type=str,
        nargs="+",
        help="Radar file(s), e.g. addison.tx-20170329-071008.netcdf.gz "
        "(bare names are resolved in ./input/; sorted order = time window)",
        required=True,
    )
    parser.add_argument(
        "-o",
        "--outdir",
        metavar="OUTPUT_LOCATION",
        type=str,
        default=".",
        help="Directory to write workflow.yml into (default: project root)",
    )

    args = parser.parse_args()
    outdir = os.path.abspath(args.outdir)
    os.makedirs(outdir, exist_ok=True)

    radar_files = [resolve_radar_file(f) for f in args.files]
    CASAWorkflow(outdir, radar_files).generate_workflow()
