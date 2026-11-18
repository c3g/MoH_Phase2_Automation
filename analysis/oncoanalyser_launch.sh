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
    echo " -g <group>                      Sample group for which to construct sample sheet and launch analysis. To be used instead of -s <sample> or -r <readset>."
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
if [[ "$sample" && "$group" ]]; then
    echo -e "ERROR: Arguments -r, -s and -g are mutually exclusive. Supply only one.\n"
    usage
fi

if [[ "$readset" && "$sample" ]]; then
    echo -e "ERROR: Arguments -r, -s and -g are mutually exclusive. Supply only one.\n"
    usage
fi

# mutually exclusive arguments
if [[ "$readset" && "$group" ]]; then
    echo -e "ERROR: Arguments -s and -g are mutually exclusive. Supply only one.\n"
    usage
fi

# mandatory arguments
if [[ ! "$readset" && ! "$sample" && ! "$group" ]]; then
    echo -e "ERROR: Missing mandatory argument -r, -s or -g.\n"
    usage
fi

source ~/project_tracking_cli/.venv/bin/activate
# TBD WHERE PHASE2 will be run? MOH dir has a lot of files from phase 1. Better to start fresh?
MOH_DIR=/project/60007/MOH_PHASE2

if [[ "$readset" ]]; then
    # find readset sample
    READSET_ID=`pt-cli --url-root https://project-tracking.c3g-app.dev-sd4h.ca/ --project MOH-Q route "/project/MOH-Q/readsets?json={\"readset_name\":\"${readset}\"}" \
    | jq -c '.DB_ACTION_OUTPUT[] | .id'`
    sample=`pt-cli --url-root https://project-tracking.c3g-app.dev-sd4h.ca/ --project MOH-Q route "/project/MOH-Q/readsets/${READSET_ID}/samples" \
    | jq -r -c '.DB_ACTION_OUTPUT[] | .name'`
fi
if [[ "$sample" ]]; then
    # find group(s) for sample
    group=`pt-cli --url-root https://project-tracking.c3g-app.dev-sd4h.ca/ --project MOH-Q sample_group list --sample_name $sample \
       | jq -r -c '.[] | select(.deleted == false and .deprecated == false) | .name'`
fi
# check to see if oncoanalyser is currently running
for GROUP in $group; do
    ret=$(~/MoH_Phase2_Automation/analysis/check_operations.py -g ${GROUP} 2>&1 || true)
    if [[ "$ret" == *\"decision\":\ \"GO\"* ]]; then 
        echo "Oncoanalyser not yet launched for all readsets of group ${GROUP}."
    else
        echo "$ret"
        echo "Not ready to launch oncoanalyser for group ${GROUP}."
        break
    fi

    CASE="${GROUP%_*}"
    ANALYSIS_DIR=${MOH_DIR}/${CASE}/${GROUP}
    mkdir -p ${ANALYSIS_DIR}/tmp
    ret=$(pt-cli --url-root https://project-tracking.c3g-app.dev-sd4h.ca/ --project MOH-Q digest oncoanalyser_samplesheet --sample_group_name $GROUP --endpoint cardinal -o ${ANALYSIS_DIR}/tmp 2>&1 || true)
    if [[ "$ret" == *WARNING* ]]; then 
        echo $ret
        echo "Not ready to launch oncoanalyser for group ${GROUP}."
        break
    fi

    tmp_sheet=${ANALYSIS_DIR}/tmp/${GROUP}.samplesheet.csv

    if grep -q "tumor,dna" ${tmp_sheet} && grep -q "normal,dna" ${tmp_sheet}; then
        echo "Ready to launch oncoanalyser for group ${GROUP}."
    else
        echo "Not ready to launch oncoanalyser for group ${GROUP}."
        break
    fi

    TIMESTAMP=$(date +%FT%H.%M.%S)
    ~/MoH_Phase2_Automation/analysis/create_samplesheet.sh ${NUCLEIC_ACID_TYPE} -g ${GROUP} -o ${ANALYSIS_DIR}/samplesheets/${TIMESTAMP} && \
    # create oncoanalyser submission script
    ~/MoH_Phase2_Automation/analysis/create_oncoanalyser_submission.sh -g ${GROUP} -d ${ANALYSIS_DIR} -t ${TIMESTAMP} && \
    ONCOANALYSER_JSON=${ANALYSIS_DIR}/${GROUP}.oncoanalyser.json && \
    # add oncoanalyser launch json and ingest into DB to set operation to PENDING
    ~/MoH_Phase2_Automation/analysis/oncoanalyser2json.py -i ${ANALYSIS_DIR} -g ${GROUP} -t ${TIMESTAMP} -o ${ONCOANALYSER_JSON} && \
    pt-cli --url-root https://project-tracking.c3g-app.dev-sd4h.ca/ --project MOH-Q ingest analysis --input-json ${ONCOANALYSER_JSON} && \
    sbatch ${ANALYSIS_DIR}/${GROUP}.oncoanalyser_${TIMESTAMP}.submit && echo "Oncoanalyser launched for ${GROUP}."
done
# do second ingest to set to running? Decide on trigger.
