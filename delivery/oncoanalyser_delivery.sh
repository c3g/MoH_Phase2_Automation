#!/bin/bash

THIS_SCRIPT=$(basename "$0")

usage() {
    echo "Usage: $THIS_SCRIPT -h [-d destination] [-g group]"
    echo "Usage:"
    echo " -h               Display this help message."
    echo " -d               Destination where to deliver results. (Default: c3g-data-repos)."
    echo " -g               Group for which to transfer results."
}
while getopts 'hd::g:' OPTION; do
    case "$OPTION" in
        d) 
            dest="$OPTARG" 
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

# mandatory argument
if [[ ! "$group" ]]; then
    echo -e "ERROR: Missing mandatory argument -g.\n"
    usage
fi

### take page from phase 1, use globus for delivery
