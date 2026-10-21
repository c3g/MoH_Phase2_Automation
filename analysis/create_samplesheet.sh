#!/usr/bin/env bash

### WORK IN PROGRESS ###

THIS_SCRIPT=$(basename "$0")

usage() {
    echo "script usage: $THIS_SCRIPT -h [-s sample] [-n nucleic_acid_type] [-g group] [-o output_dir]"
    echo "Usage:"
    echo " -h                               Display this help message."
    echo " -s <sample>                      Sample ('CaseType') for which to construct sample sheet. Should be a tumor or RNA sample."
    echo " -n <nucleic_acid_type>           Nucleic_acid_type to be considered for the sample sheet (either DNA or RNA, Default: both)."
    echo " -g <group>                       Sample group for which to construct sample sheet. To be used instead of -s <sample>."
    echo " -o <output_dir>                  Output directory where to write sample sheet. (Default: current directory)."
    exit 1                      
}

while getopts 'hs::n::g::o:' OPTION; do
    case "$OPTION" in
        s)
            sample="$OPTARG"
            ;;
        n)
            nucleic_acid_type="$OPTARG"
            ;;
        g)
            sample_group="$OPTARG"
            ;;
        o)
            output_dir="$OPTARG"
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
    echo -e "ERROR: Arguments -s and -g are mutually exclusive. Supply only one.\n"
    usage
fi

# mandatory arguments
if [[ ! "$sample" && ! "$sample_group" ]]; then
    echo -e "ERROR: Missing mandatory argument -s or -g.\n"
    usage
fi

if [ "$nucleic_acid_type" ]; then
    TYPE_ARG="--nucleic_acid_type ${nucleic_acid_type}"
else
    TYPE_ARG=""
fi

# source project tracking client environment
source pt-cli_venv/bin/activate

# call client to get samplesheet for Case/CaseType
# exact call TBD
if [[ "$sample" ]]; then
    SAMPLE_GROUPS=`pt-cli --url-root https://c3g-portal.dev-sd4h.ca --project MOH-Q sample_group list --sample_name ${sample}` # find group name for sample
    GROUP_NAME=$(echo "$SAMPLE_GROUPS" | jq -r '.[0].name')
else
    GROUP_NAME=${sample_group}
fi

if [[ "$output_dir" ]]; then
    OUTPUT_DIR="-o ${output_dir}/"
else
    OUTPUT_DIR=""

pt-cli --url-root https://c3g-portal.dev-sd4h.ca --project MOH-Q digest oncoanalyser_samplesheet --sample_group_name ${GROUP_NAME} --endpoint cardinal ${TYPE_ARG} ${OUTPUT_DIR}

