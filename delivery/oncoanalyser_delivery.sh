#!/usr/bin/env bash

# Deliver results/ of one oncoanalyser run to the bucket with Globus
# using Globus sync 
# Only called once the run is COMPLETED

set -eo pipefail
umask 007

THIS_SCRIPT=$(basename "$0")

usage() {
    echo "script usage: $THIS_SCRIPT -h -i <run_dir> -g <group> [-d <destination>]"
    echo "Usage:"
    echo " -h                  Display this help message."
    echo " -i <run_dir>        Run folder of the analysis (holds results)."
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
SRC_EP="00aa3ab7-8dc3-4c89-81bc-1d006c31a36f"
SRC_BASE_PATH="/project/60007/MOH_PHASE2/MAIN"

# Destination: the bucket
case "$destination" in
    c3g-data-repos)
        DEST_EP="973962f0-127f-401c-a428-26a9fae7417e"
        DEST_LOC="MOH-Q"
        ;;
    *)
        echo "ERROR: Unknown destination: $destination"
        exit 1
        ;;
esac

# Run folder
run_dir=$(realpath "$run_dir")
src=$run_dir/results

if [[ "$src" != "$SRC_BASE_PATH"/* ]]; then #make sure rundir path starts with base path
    echo "ERROR: $src not under the Globus collection base path $SRC_BASE_PATH."
    exit 1
fi

# Where results go in the bucket: MOH-Q/<institution>/<cohort>/<specimen>/<group>/results
specimen=$(basename "$(dirname "$run_dir")")
# cohort + institution of the specimen from the DB
unset PYTHONPATH
source ~/project_tracking_cli/.venv/bin/activate
read -r cohort institution < <(pt-cli --url-root https://project-tracking.c3g-app.dev-sd4h.ca/ --project MOH-Q route "/project/MOH-Q/specimens?json={\"specimen_name\":\"${specimen}\"}" \
    | jq -r '.DB_ACTION_OUTPUT[0] | "\(.cohort) \(.institution)"') || true
if [ -z "$institution" ] || [ "$cohort" = "null" ] || [ "$institution" = "null" ]; then
    echo "ERROR: cohort/institution of $specimen not found in the DB."
    exit 1
fi
DEST_PATH="$institution/$cohort/$specimen/$group/results"

#TIMESTAMPS
TIMESTAMP=$(date +%FT%H.%M.%S) #for josn lists filenamses
timestamp_start=$(date "+%Y-%m-%dT%H.%M.%S") #tell db the delivery starttime

# LIST ADN JSONS
LISTFILE="$run_dir/tmp/${group}_${TIMESTAMP}_${destination}_delivery.list" #batchfile for transfer
TRANSFERRED_JSON="$run_dir/tmp/${group}_${TIMESTAMP}_${destination}_transferred.json" #keep all files copied by globus
DELIVERY_JSON="$run_dir/tmp/${group}_${TIMESTAMP}_${destination}_delivery.json" #output of delivery2json

# One line batchfile for the whole results folder
echo "--recursive ${src#"$SRC_BASE_PATH"} $DEST_PATH" > "$LISTFILE"

# Load globus module
module use /cvmfs/soft.mugqic/CentOS6/modulefiles
module load mugqic/globus-cli/3.24.0

ENV_DIR="$HOME/.config/globus_cli"
ENV_FILE="$ENV_DIR/Cardinal_to_c3g-data-reposMOH-Q.sh"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: Expected environment file '$ENV_FILE' not found." >&2
    exit 1
fi
source "$ENV_FILE"

sub_id="$(globus task generate-submission-id)"
# Start the batch transfer
task_id="$(globus transfer --sync-level mtime --jmespath 'task_id' --format=UNIX --submission-id "$sub_id" --label "$group" --batch "$LISTFILE" $SRC_EP $DEST_EP)"
echo -e "Waiting on 'globus transfer' task '$task_id'.\nTo monitor the transfer see: https://app.globus.org/activity/$task_id/overview"

until status=$(globus task show "$task_id" --jmespath status --format=UNIX 2>/dev/null) \
      && [[ "$status" =~ ^(SUCCEEDED|FAILED)$ ]]; do
    sleep 60
done

if [ "$status" != "SUCCEEDED" ]; then
    echo "$task_id failed! ($status)"
    exit 1
fi

globus task show --successful-transfers "$task_id" -F json > "$TRANSFERRED_JSON"
module unload mugqic/globus-cli/3.24.0
timestamp_end=$(date "+%Y-%m-%dT%H.%M.%S")

# Delivery json -> DB
~/MoH_Phase2_Automation/delivery/delivery2json.py --input "$TRANSFERRED_JSON" --source $SRC_PLATFORM --destination $destination --output "$DELIVERY_JSON" --operation_cmd_line "globus transfer --sync-level mtime --jmespath 'task_id' --format=UNIX --submission-id $sub_id --label $group --batch $LISTFILE $SRC_EP $DEST_EP" --start $timestamp_start --stop $timestamp_end
echo "Ingesting delivery $DELIVERY_JSON..."
pt-cli --url-root https://project-tracking.c3g-app.dev-sd4h.ca/ --project MOH-Q ingest delivery --input-json "$DELIVERY_JSON" --no-delete
