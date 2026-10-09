#!/usr/bin/env python3
"""CASA Wind workflow generator (Pegasus 5).

Generates workflow.yml with the transformation and replica catalogs embedded,
plus pegasus.properties, so it plans with a plain
`pegasus-plan --conf pegasus.properties -s compute -o local workflow.yml` — no
external tc.txt/rc.txt and no --input-dir.

Sites follow pegasus-isi/pegasus-gromacs: jobs run on a site named "compute",
defined by a centrally hosted site catalog (-s access-pegasus.yml, ...;
https://github.com/pegasushub/pegasus-site-catalogs) or by one in
~/.pegasusrc. The generator writes no site catalog; on a plain HTCondor pool
with no site catalog, use -e condorpool (Pegasus builds that site itself).
It does not plan or submit: run the pegasus-plan command it prints, or use
CASA-Wind-Workflow.ipynb.

Given a window of radar sweep files (addison.tx-YYYYMMDD-HHMMSS.netcdf.gz):
  1. gunzip decompresses each sweep
  2. um_vel computes the max wind velocity over the window
  3. merged_netcdf2png renders the velocity field to a PNG
  4. mvt vectorizes the velocity field to GeoJSON
  5. pointalert intersects it with hospital locations into an alert GeoJSON
"""

import os
import sys
from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path

from Pegasus.api import (
    OS,
    Arch,
    Container,
    Directory,
    File,
    FileServer,
    Job,
    Operation,
    PegasusClientError,
    Properties,
    ReplicaCatalog,
    Site,
    SiteCatalog,
    Transformation,
    TransformationCatalog,
    Workflow,
)

# Per-tool resource configuration for the transformation catalog.
TOOL_CONFIGS = {
    "gunzip": {"memory": "1 GB", "cores": 1},
    "um_vel": {"memory": "4 GB", "cores": 1},
    "merged_netcdf2png": {"memory": "2 GB", "cores": 1},
    "mvt": {"memory": "4 GB", "cores": 1},
    "pointalert": {"memory": "2 GB", "cores": 1},
}

AUX_INPUTS = ("max_wind.png", "pointAlert_config.txt", "hospital_locations.geojson")


class CASAWorkflow(object):
    wf = None
    sc = None
    tc = None
    rc = None
    props = None

    def __init__(self, outdir, radar_files,
                 container_sif="Apptainer/CASA_Wind_Container.sif"):
        self.outdir = outdir
        self.radar_files = radar_files
        self.wf_dir = str(Path(__file__).parent.resolve())
        self.container_sif = container_sif
        self.shared_scratch_dir = os.path.join(outdir, "scratch")
        self.local_storage_dir = os.path.join(outdir, "output")
        self.dagfile = os.path.join(outdir, "workflow.yml")
        self.propsfile = os.path.join(outdir, "pegasus.properties")

    def write(self):
        """Write workflow.yml (catalogs embedded) and pegasus.properties."""
        if self.sc is not None:
            self.wf.add_site_catalog(self.sc)
        self.wf.add_transformation_catalog(self.tc)
        self.wf.add_replica_catalog(self.rc)
        self.props.write(self.propsfile)
        self.wf.write(self.dagfile)

    # ------------------------------------------------------------------
    # Plan / run / monitor (thin wrappers over the Pegasus API Workflow
    # object, for interactive use e.g. from a Jupyter notebook)
    # ------------------------------------------------------------------
    def plan_submit(self, exec_site_name="compute", raise_errors=False):
        try:
            self.wf.plan(
                conf=self.propsfile,
                dir=os.path.join(self.outdir, "submit"),
                sites=[exec_site_name],
                output_sites=["local"],
                cleanup="leaf",
                verbose=1,
                submit=True,
            )
        except PegasusClientError as e:
            print(e)
            if raise_errors:
                raise

    def status(self):
        try:
            self.wf.status(long=True)
        except PegasusClientError as e:
            print(e)

    def wait(self):
        try:
            self.wf.wait()
        except PegasusClientError as e:
            print(e)

    def statistics(self):
        try:
            self.wf.statistics()
        except PegasusClientError as e:
            print(e)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    def create_pegasus_properties(self, hosted_site_catalog=None):
        self.props = Properties()
        # This is the name of the application for analytics
        self.props["pegasus.metrics.app"] = "CASA-WIND"
        self.props["pegasus.transfer.threads"] = "16"
        if hosted_site_catalog:
            # Use one of Pegasus' centrally hosted site catalogs instead of
            # a locally generated one. pegasus-plan downloads and caches the
            # named file from the catalog repository at plan time.
            # https://pegasus.isi.edu/documentation/reference-guide/catalogs.html#centrally-hosted-site-catalogs
            self.props["pegasus.catalog.site.repo.file"] = hosted_site_catalog

    # ------------------------------------------------------------------
    # Site Catalog
    #
    # Not used by the CLI below — pegasus-plan resolves the site catalog
    # from a centrally hosted one instead (see -s/--hosted-site-catalog and
    # create_pegasus_properties above). Kept for programmatic/notebook use
    # when a self-contained, locally generated HTCondor site catalog is
    # wanted.
    # ------------------------------------------------------------------
    def create_sites_catalog(self, exec_site_name="compute"):
        self.sc = SiteCatalog()

        local = Site("local", arch=Arch.X86_64, os_type=OS.LINUX)
        local.add_directories(
            Directory(
                Directory.SHARED_SCRATCH, self.shared_scratch_dir
            ).add_file_servers(
                FileServer("file://" + self.shared_scratch_dir, Operation.ALL)
            ),
            Directory(
                Directory.LOCAL_STORAGE, self.local_storage_dir
            ).add_file_servers(
                FileServer("file://" + self.local_storage_dir, Operation.ALL)
            ),
        )

        exec_site = Site(exec_site_name, arch=Arch.X86_64, os_type=OS.LINUX)
        exec_site.add_condor_profile(universe="vanilla")
        exec_site.add_pegasus_profile(style="condor", data_configuration="condorio")

        self.sc.add_sites(local, exec_site)

    # ------------------------------------------------------------------
    # Transformation Catalog
    # ------------------------------------------------------------------
    def create_transformation_catalog(self, exec_site_name="compute"):
        self.tc = TransformationCatalog()

        # A local Apptainer .sif built with `apptainer build` from
        # Apptainer/CASA_Wind_Container.def. Pegasus stages the file like
        # any other input, so image_site is the site where the .sif
        # physically lives (the submit host = "local").
        sif_path = (
            self.container_sif
            if os.path.isabs(self.container_sif)
            else os.path.join(self.wf_dir, self.container_sif)
        )
        if not os.path.exists(sif_path):
            print(
                f"warning: Apptainer image not found at {sif_path} — build it "
                f"first with: apptainer build {sif_path} "
                f"Apptainer/CASA_Wind_Container.def",
                file=sys.stderr,
            )
        wind_container = Container(
            "wind_image",
            container_type=Container.SINGULARITY,
            image="file://" + sif_path,
            image_site="local",
        )
        self.tc.add_containers(wind_container)

        # gunzip runs in the container too (the image ships /bin/gunzip), so
        # the workflow needs nothing installed on the workers.
        for name, pfn in (
            ("gunzip", "/bin/gunzip"),
            ("um_vel", "/opt/UM_VEL/UM_VEL"),
            ("merged_netcdf2png", "/opt/netcdf2png/merged_netcdf2png"),
            ("mvt", "/opt/mvt/mvt"),
            ("pointalert", "/opt/pointAlert/pointAlert"),
        ):
            self.tc.add_transformations(
                Transformation(
                    name,
                    site=exec_site_name,
                    pfn=pfn,
                    is_stageable=False,
                    container=wind_container,
                    arch=Arch.X86_64,
                    os_type=OS.LINUX,
                ).add_pegasus_profile(
                    memory=TOOL_CONFIGS[name]["memory"],
                    cores=TOOL_CONFIGS[name]["cores"],
                )
            )

    # ------------------------------------------------------------------
    # Replica Catalog
    # ------------------------------------------------------------------
    def create_replica_catalog(self):
        self.rc = ReplicaCatalog()
        input_dir = os.path.join(self.wf_dir, "input")
        for aux in AUX_INPUTS:
            self.rc.add_replica("local", aux, "file://" + os.path.join(input_dir, aux))

        for path in self.radar_files:
            self.rc.add_replica("local", os.path.basename(path), "file://" + path)

    # ------------------------------------------------------------------
    # Workflow DAG
    # ------------------------------------------------------------------
    def create_workflow(self):
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.wf = wf = Workflow("casa-wind-wf-%s" % ts)
        wf.add_metadata(name="CASA Wind")

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


def resolve_radar_file(name):
    """Absolute path of a radar file given bare name or path."""
    if os.path.isfile(name):
        return os.path.abspath(name)
    candidate = os.path.join("input", os.path.basename(name))
    if os.path.isfile(candidate):
        return os.path.abspath(candidate)
    raise SystemExit(f"error: radar file '{name}' not found (looked in ./input/)")


def main():
    parser = ArgumentParser(
        description="CASA Wind Workflow",
        epilog="Writes workflow.yml and pegasus.properties; it does not plan "
        "or submit. Run the pegasus-plan command it prints, or use "
        "CASA-Wind-Workflow.ipynb.",
    )
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
        help="Directory to write workflow.yml and pegasus.properties into "
        "(default: project root)",
    )
    parser.add_argument(
        "--container-sif",
        metavar="PATH",
        type=str,
        default="Apptainer/CASA_Wind_Container.sif",
        help="Path to the Apptainer .sif image, absolute or relative to the "
        "workflow directory (default: Apptainer/CASA_Wind_Container.sif)",
    )
    parser.add_argument(
        "-s",
        "--hosted-site-catalog",
        metavar="FILE",
        type=str,
        default=None,
        help="Name of a Pegasus centrally hosted site catalog to plan against "
        "(e.g. access-pegasus.yml), instead of a locally generated one. Sets "
        "pegasus.catalog.site.repo.file; see "
        "https://pegasus.isi.edu/documentation/reference-guide/catalogs.html"
        "#centrally-hosted-site-catalogs",
    )
    parser.add_argument(
        "-e",
        "--execution-site-name",
        metavar="STR",
        type=str,
        default="compute",
        help="Execution site name (default: compute; use condorpool on a "
        "plain HTCondor pool with no site catalog)",
    )

    args = parser.parse_args()
    outdir = os.path.abspath(args.outdir)
    os.makedirs(outdir, exist_ok=True)

    radar_files = [resolve_radar_file(f) for f in args.files]
    workflow = CASAWorkflow(outdir, radar_files,
                            container_sif=args.container_sif)
    workflow.create_pegasus_properties(hosted_site_catalog=args.hosted_site_catalog)
    workflow.create_transformation_catalog(exec_site_name=args.execution_site_name)
    workflow.create_replica_catalog()
    workflow.create_workflow()
    workflow.write()

    print(f"Workflow written to {workflow.dagfile}")
    print(
        f"Plan and submit: pegasus-plan --conf {workflow.propsfile} "
        f"--dir {os.path.join(outdir, 'submit')} "
        f"-s {args.execution_site_name} -o local --submit {workflow.dagfile}"
    )


if __name__ == "__main__":
    main()
