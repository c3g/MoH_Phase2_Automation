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
# call client to get samplesheet for Case/CaseType
# exact call TBD
pt-cli --url-root http://127.0.0.1:5000 digest readset_file --specimen_name 'MoHQ-GC-31-598' 
