#!/usr/bin/env bash

### WORK IN PROGRESS ###

THIS_SCRIPT=$(basename "$0")

usage() {
    echo "script usage: $THIS_SCRIPT -h [-l location] [-d destination] [-s sample]"
    echo "Usage:"
    echo " -h                               Display this help message."
    echo " -s <sample>                      Sample ('CaseType') for which to construct sample sheet"
    echo " -n <nucleic_acid_type>           nucleic_acid_type to be considered for the sample sheet (either DNA or RNA, Default: both)."
    exit 1                      
}

while getopts 'hs::n:' OPTION; do
    case "$OPTION" in
        s)
            sample="$OPTARG"
            ;;
        n)
            nucleic_acid_type="$OPTARG"
            ;;
        h)
            usage
            ;;
        ?)
            usage
            ;;
    esac
done

# mandatory arguments
if [ ! "$sample"  ]; then
    echo -e "ERROR: Missing mandatory argument -s.\n"
    usage
fi

# source project tracking client environment
source pt-cli_venv/bin/activate

# call client to get samplesheet for Case/CaseType
# exact call TBD
SAMPLE_GROUPS=`pt-cli --url-root https://c3g-portal.dev-sd4h.ca --project MOH-Q sample_group list --sample_name ${sample}` # find group name for sample
GROUP_NAME=$(echo "$SAMPLE_GROUPS" | jq -r '.[0].name')
pt-cli --url-root https://c3g-portal.dev-sd4h.ca --project MOH-Q digest oncoanalyser_samplesheet --sample_group_name ${GROUP_NAME} --endpoint cardinal

