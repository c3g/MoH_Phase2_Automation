#!/usr/bin/env bash

### WORK IN PROGRESS ###

THIS_SCRIPT=$(basename "$0")

usage() {
    echo "script usage: $THIS_SCRIPT -h [-r run_processing_json] [-l lane]"
    echo "Usage:"
    echo " -h                        Display this help message."
    echo " -r <run_processing_json>  Run Processing json."
    echo " -l <lane>                 Lane to transfer."
    exit 1
    }

while getopts 'hr:l:' OPTION; do
    case "$OPTION" in
        r)
            run_processing_json="$OPTARG"
            ;;
        l)
            lane="$OPTARG"
            ;;
        h)
            usage
            ;;
        ?)
            usage
            ::
    esac
done

if [ ! "$run_processing_json"  ] || [ ! "$lane"  ]; then
    echo -e "ERROR: Missing mandatory argument -r and/or -l.\n"
    usage
fi

#ROBOT_EP="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/globus_collections.json"

#destination_lowercase="${destination,,}"
#DEST_EP=$(jq -r --arg dest "$destination_lowercase" '.robot_endpoints[$dest].uuid' "$ROBOT_EP")
DEST_EP="2cef98ab-568d-4136-9e0c-8391215dd929"
DEST_LOC="MOH-Q"
destination="c3g-data-repos"
# Abacus Endpoint
ABA_EP="01389a74-7832-499b-8226-c6ff10d69731"
SRC_BASE_PATH="/nb/Research/freezeman-processing"

runfolder=$(jq -r '.run_name' "$run_processing_json")

# Temporary File location, you may want to change it to your scratch for easier clean up.
TRANSFER_JSON_DIR='/lb/project/mugqic/projects/mjaniak/MOH_Phase2/Transfer_json'
TEMP='/lb/project/mugqic/projects/mjaniak/MOH_Phase2/TEMP'
TIMESTAMP=$(date +%FT%H.%M.%S)
LOGFILE="${runfolder}_${TIMESTAMP}_${destination}_transfer.log"
LISTFILE="${runfolder}_${TIMESTAMP}_${destination}_transfer.list"
LISTFILE_FULLPATH="${runfolder}_${TIMESTAMP}_${destination}_transfer_fullpath.list"
timestamp_start=$(date "+%Y-%m-%dT%H.%M.%S")

touch "$TEMP/$LOGFILE"
touch "$TEMP/$LISTFILE"
echo "Log file of transfer from Abacus to $destination" > "$TEMP/$LOGFILE"


jq --arg lane "$lane" -r '
  .specimen[]? |
  .specimen_institution as $institution |
  .specimen_name as $specimen |
  .specimen_cohort as $cohort |
  .sample[]? | 
  .sample_name as $sample_name | 
  .readset[]? | 
  select(.readset_lane == $lane) | 
  .readset_name as $readset_name |
  .file[]? | 
  select(.location_uri != null) | 
  "\($institution) \($specimen) \($cohort) \($sample_name) \($readset_name) \(.location_uri | sub("^abacus://"; ""))"
  ' "$run_processing_json" | while read -r institution specimen cohort sample_name readset_name file; do
  file_basename=$(basename "$file")
  echo "${file#"$SRC_BASE_PATH"} ${DEST_LOC#"$DEST_BASE_PATH"}/$institution/$cohort/$specimen/$file_basename" >> "$TEMP/$LISTFILE"
  echo "${readset_name} $file $DEST_LOC/$institution/$cohort/$specimen/$file_basename" >> "$TEMP/$LISTFILE_FULLPATH"
  echo "$file,$sample_name/$file_basename" >> "$TEMP/$LOGFILE"
done

# Load globus module
module load mugqic/globus-cli/3.24.0
# Now using Robot account to do the transfer
ENV_DIR="$HOME/.config/globus_cli"

# Generate and store a UUID for the submission-id
sub_id="$(globus task generate-submission-id)"
# Start the batch transfer
task_id="$(globus transfer --sync-level mtime --jmespath 'task_id' --format=UNIX --submission-id "$sub_id" --label "$runfolder" --batch "$TEMP/$LISTFILE" $ABA_EP $DEST_EP)"

echo -e "Waiting on 'globus transfer' task '$task_id'.\nTo monitor the transfer see: https://app.globus.org/activity/$task_id/overview"
globus task wait "$task_id" --polling-interval 60 -H
if [ $? -eq 0  ]; then
    TRANSFER_JSON="$TRANSFER_JSON_DIR/${LISTFILE/.list/.json}"
    module unload mugqic/globus-cli/3.24.0
    timestamp_end=$(date "+%Y-%m-%dT%H.%M.%S")
    source ~/project_tracking_cli/.venv/bin/activate
    ~/MoH_Phase2_Automation/run_processing/transfer2json.py --input $TEMP/$LISTFILE_FULLPATH --source "abacus" --destination $destination --output $TRANSFER_JSON --operation_cmd_line "globus transfer --sync-level mtime --jmespath 'task_id' --format=UNIX --submission-id $sub_id --label $runfolder --batch $TEMP/$LISTFILE $ABA_EP $DEST_EP" --start $timestamp_start --stop $timestamp_end
    echo "Ingesting transfer $TRANSFER_JSON..."
    pt-cli --url-root https://project-tracking.c3g-app.dev-sd4h.ca/ --project MOH-Q ingest transfer --input-json $TRANSFER_JSON
   
    # add ping to jenkins for finished transfer
    jq -r '
      .readset[]? |
      .readset_name as $readset_name |
      "\($readset_name)"
    ' "$TRANSFER_JSON" | while read -r readset_name; do
    curl -v \
         -H "Content-Type: application/json" \
         -X POST \
         -d '{"readset_name": "'"$readset_name"'"}' \
         "https://jenkins.c3g-app.sd4h.ca/generic-webhook-trigger/invoke?token=7BM5klS2iGh0TmIY"
    sleep 10
    done
else
    echo "$task_id failed!"
fi
