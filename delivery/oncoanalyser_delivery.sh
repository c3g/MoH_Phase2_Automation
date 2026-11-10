#!/usr/bin/env bash

# Deliver results/<group>/ of one oncoanalyser run to the bucket with Globus
# using Globus sync 
# Only called once the run is COMPLETED

set -eo pipefail
umask 007

THIS_SCRIPT=$(basename "$0")

usage() {
    echo "script usage: $THIS_SCRIPT -h -i <run_dir> -g <group> [-d <destination>]"
    echo "Usage:"
    echo " -h                  Display this help message."
    echo " -i <run_dir>        Run folder of the analysis (holds results/<group>/ and <group>.oncoanalyser.json)."
    echo " -g <group>          Group to deliver."
    echo " -d <destination>    Destination of the delivery (Default: c3g-data-repos)."
    exit 1
}

destination="c3g-data-repos"

while getopts 'hi:g:d:' OPTION; do
    case "$OPTION" in
        i) run_dir="$OPTARG" ;;
        g) group="$OPTARG" ;;
        d) destination="$OPTARG" ;;
        *) usage ;;
    esac
done

if [[ ! "$run_dir" || ! "$group" ]]; then
    echo -e "ERROR: Missing mandatory argument -i and/or -g.\n"
    usage
fi

# Source: Cardinal
SRC_PLATFORM="cardinal"
SRC_EP="ee0ec49b-7bf7-4b25-9030-2e19c03476ca" # from MoH1 globus_collections.json
SRC_BASE_PATH="/project/60007/MOH_PHASE2"

# Destination: the bucket (same as phase 2 raw data)
case "$destination" in
    c3g-data-repos)
        DEST_EP="2cef98ab-568d-4136-9e0c-8391215dd929"
        DEST_LOC="MOH-Q"
        ;;
    *)
        echo "ERROR: Unknown destination: $destination"
        exit 1
        ;;
esac

# Run folder
run_dir=$(realpath "$run_dir")
src=$run_dir/results/$group
analysis_json=$run_dir/$group.oncoanalyser.json

if [ ! -d "$src" ] || [ ! -f "$analysis_json" ]; then
    echo "ERROR: $src or $analysis_json not found."
    exit 1
fi
# Globus needs the path inside the collection
if [[ "$src" != "$SRC_BASE_PATH"/* ]]; then
    echo "ERROR: $src is not under the Globus collection base path $SRC_BASE_PATH."
    exit 1
fi

# Where results go in the bucket: MOH-Q/<institution>/<cohort>/<specimen>/<group>/results
specimen=$(basename "$(dirname "$run_dir")")
# cohort + institution of the specimen from the DB
source ~/project_tracking_cli/.venv/bin/activate
read -r cohort institution < <(pt-cli --url-root https://project-tracking.c3g-app.dev-sd4h.ca/ --project MOH-Q route "/project/MOH-Q/specimens?json={\"specimen_name\":\"${specimen}\"}" \
    | jq -r '.DB_ACTION_OUTPUT[0] | "\(.cohort) \(.institution)"') || true
if [ -z "$institution" ] || [ "$cohort" = "null" ] || [ "$institution" = "null" ]; then
    echo "ERROR: cohort/institution of $specimen not found in the DB."
    exit 1
fi
DEST_PATH="$DEST_LOC/$institution/$cohort/$specimen/$group/results"

# TO ADD: list and globus transfer and json
