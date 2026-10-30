#/bin/bash

### WORK IN PROGRESS ###

# Script will orchestrate sample sheet construction (separate python script)
# and oncoanalyser submit script generation, followed by oncoanalyser launch.
# After launch, operation is added to DB as running to prevent concurrent launches.
# triggered via jenkins when new data has finished transferring to MoH bucket


THIS_SCRIPT=$(basename "$0")

usage() {
    echo "script usage: $THIS_SCRIPT -h [-r readset] [-s sample] [-g group]"
    echo "Usage:"
    echo " -h                               Display this help message."
    echo " -r <readset>                     Readset for which to construct sample sheet and launch analysis. To be used instead of -s <sample> or -g <group>."
    echo " -s <sample>                      Sample for which to construct sample sheet and launch analysis. To be used instead of -r <readset> or -g <group>."
    echo " -g <group>                       Sample group for which to construct sample sheet and launch analysis. To be used instead of -s <sample> or -r <readset>."
    exit 1                      
}

while getopts 'hr::s::g:' OPTION; do
    case "$OPTION" in
        r)
            readset="$OPTARG"
            ;;
        s)
            sample="$OPTARG"
            ;;
        g)
            group="$OPTARG"
            ;;
        h)
            usage
            ;;
        ?)
            usage
            ;;
    esac
done

# mutually exclusive arguments
if [[ "$sample" && "$sample_group" ]]; then
    echo -e "ERROR: Arguments -r, -s and -g are mutually exclusive. Supply only one.\n"
    usage
fi

if [[ "$readset" && "$sample" ]]; then
    echo -e "ERROR: Arguments -r, -s and -g are mutually exclusive. Supply only one.\n"
    usage
fi

# mutually exclusive arguments
if [[ "$readset" && "$sample_group" ]]; then
    echo -e "ERROR: Arguments -s and -g are mutually exclusive. Supply only one.\n"
    usage
fi

# mandatory arguments
if [[ ! "$readset" && ! "$sample" && ! "$sample_group" ]]; then
    echo -e "ERROR: Missing mandatory argument -r, -s or -g.\n"
    usage
fi

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
TIMESTAMP=$(date +%FT%H.%M.%S)
~/MoH_Phase2_Automation/analysis/create_samplesheet.sh ${NUCLEIC_ACID_TYPE} -g ${GROUP} -o ${ANALYSIS_DIR}/samplesheets/${TIMESTAMP}

# create oncoanalyser submission script
~/MoH_Phase2_Automation/analysis/create_oncoanalyser_submission.sh -g ${GROUP} -d ${ANALYSIS_DIR} -t ${TIMESTAMP}

sbatch ${ANALYSIS_DIR}/${GROUP}.oncoanalyser_${TIMESTAMP}.submit

echo "Oncoanalyser launched for $GROUP."

ONCOANALYSER_JSON=${ANALYSIS_DIR}/${GROUP}.oncoanalyser.json

# add oncoanalyser launch json and ingest into DB to set operation to RUNNING
~/MoH_Phase2_Automation/analysis/oncoanalyser2json.sh -i ${ANALYSIS_DIR} -t ${TIMESTAMP} -o ${ONCOANALYSER_JSON}
pt-cli --project MOH-Q ingest analysis --input-json ${ONCOANALYSER_JSON}
