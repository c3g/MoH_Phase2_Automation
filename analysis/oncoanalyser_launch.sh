#/bin/bash

### WORK IN PROGRESS ###

# script will orchestrate sample sheet construction (separate python script) and oncoanalyser launch
# triggered via jenkins when new data has finished transferring to MoH bucket


THIS_SCRIPT=$(basename "$0")

usage() {
    echo "script usage: $THIS_SCRIPT -h [-s sample]"
    echo "Usage:"
    echo " -h                               Display this help message."
    echo " -s <sample>                      Sample or readset (?) that has finished transferring."
    exit 1                      
}

while getopts 'hs:' OPTION; do
    case "$OPTION" in
        s)
            sample="$OPTARG"
            ;;
        h)
            usage
            ;;
        ?)
            usage
            ;;
    esac
done

# call to DB to check on status of readsets linked to the same sample

# if all readsets for sample are valid (transferred) find other members of group(s)

# if sample is RNA and DNA not yet available, do nothing

# if sample is DNA and both tumor/normal available and valid, but RNA isn't launch with DNA samplesheet only

# if sample is DNA and both tumor/normal available and valid and RNA is available launch with full samplesheet

# # if sample is RNA and DNA available, but not yet finished running, do nothing (will need to think of another trigger? Maybe upon oncoanalyser finishing?)

# if sample is RNA and DNA has already been run, launch with full sample sheet
