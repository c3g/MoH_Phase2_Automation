#/bin/bash

### WORK IN PROGRESS ###

# script will orchestrate sample sheet construction (separate python script) and oncoanalyser launch
# triggered via jenkins when new data has finished transferring to MoH bucket


THIS_SCRIPT=$(basename "$0")

# add options to pass sample or group instead of readset?
usage() {
    echo "script usage: $THIS_SCRIPT -h [-r readset]"
    echo "Usage:"
    echo " -h                               Display this help message."
    echo " -r <readset>                      Readset that has finished transferring."
    exit 1                      
}

while getopts 'hr:' OPTION; do
    case "$OPTION" in
        s)
            readset="$OPTARG"
            ;;
        h)
            usage
            ;;
        ?)
            usage
            ;;
    esac
done

source ~/project_tracking_cli/venv/bin/activate
# TBD WHERE PHASE2 will be run? MOH dir has a lot of files from phase 1. Better to start fresh?
MOH_DIR=/project/60007/MOH_PHASE2

# call to DB to check on status of other readsets linked to the same sample

# if all readsets for sample are valid (transferred) find other members of group(s)

# if sample is RNA and DNA not yet available, do nothing

# if sample is DNA and both tumor/normal available and valid, but RNA isn't launch with DNA samplesheet only

# if sample is DNA and both tumor/normal available and valid and RNA is available launch with full samplesheet

# # if sample is RNA and DNA available, but not yet finished running, do nothing (will need to think of another trigger? Maybe upon oncoanalyser finishing?)

# if sample is RNA and DNA has already been run, launch with full sample sheet
ANALYSIS_DIR=${MOH_DIR}/${CASE}/${GROUP}
~/MoH_Phase2_Automation/analysis/create_samplesheet.sh ${NUCLEIC_ACID_TYPE} -g ${GROUP} -o ${ANALYSIS_DIR}

TIMESTAMP=$(date +%FT%H.%M.%S)

# create oncoanalyser submission script
~/MoH_Phase2_Automation/analysis/create_oncoanalyser_submission.sh -g ${GROUP} -d ${ANALYSIS_DIR} -t ${TIMESTAMP}

sbatch ${ANALYSIS_DIR}/${GROUP}.oncoanalyser_${TIMESTAMP}.submit

echo "Oncoanalyser launched for $GROUP."

# add oncoanalyser launch json and ingest into DB to set operation to RUNNING
~/MoH_Phase2_Automation/analysis/oncoanalyser2json.sh -i TBD -o $oncoanalyser_json
pt-cli ingest run_processing --input-json $oncoanalyser_json
