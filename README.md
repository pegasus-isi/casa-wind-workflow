# casa-wind-workflow

Pegasus workflow for the CASA wind pipeline. Given a window of radar sweep
files (`addison.tx-YYYYMMDD-HHMMSS.netcdf.gz`), it:

1. decompresses each sweep (`gunzip`, host tool)
2. computes the max wind velocity over the window (`um_vel`)
3. renders the velocity field to a PNG (`merged_netcdf2png`)
4. vectorizes the velocity field to GeoJSON (`mvt`)
5. intersects it with hospital locations into an alert GeoJSON (`pointalert`)

Container jobs run in `pegasus/casa-wind` (Singularity, pulled from Docker
Hub) on a site named `condorpool`. A five-sweep sample window ships in
`input/`; the full test dataset lives on the `testdata` branch.

CASA container: https://hub.docker.com/r/pegasus/casa-wind

![CASA Workflow DAG](/images/casa.png)

## Usage

Generate `workflow.yml` (catalogs embedded — no external `sites.xml`/`tc.txt`/
`rc.txt` needed):

```sh
./workflow_generator.py -f input/addison.tx-*.netcdf.gz
```

`-f` takes the radar files for one window (bare names are resolved in
`./input/`; the last file's timestamp names the outputs). `-o` sets where
`workflow.yml` is written (default: project root).

Plan and submit:

```sh
./plan.sh                 # plans + submits ./workflow.yml
```

or equivalently `pegasus-plan -s condorpool -o local --submit workflow.yml`.

## PegasusAI Studio

This repo is Studio-compatible: clone it into `~/work/workflows/`, and it
appears on the Dashboard. The Generate action introspects
`workflow_generator.py` (declared in `.pegasushub.yml`), and Plan/Submit work
directly on the generated `workflow.yml`.

## Legacy files

`legacy/` holds the pre-5.0 DAX3 generator and external catalogs
(`daxgen.py`, `run_wf.sh`, `sites.xml`, `tc.txt`, `rc.txt`), superseded by
`workflow_generator.py`. They must stay out of the project root:
pegasus-plan picks up `tc.txt`/`rc.txt`/`sites.xml` from the working
directory by default, and those definitions silently shadow the catalogs
embedded in `workflow.yml` (e.g. reverting the container to Docker).
