#!/bin/bash
set -e -o pipefail

usage() {
    echo "script usage: ingest_transfer_raw_data.sh -h [-r runfolder] [-l lane] [-s sample] [-x xsample]"
    echo "Usage:"
    echo " -h                               Display this help message."
    echo " -r <runfolder>                   RunFolder found in abacus under /nb/Research/freezeman-processing/<sequencer>/<year>/<runfolder>."
    echo " -d <destination>                 Destination of the transfer (default: c3g-data-repos)."
    echo " -n <nucleic_acid_type>           nucleic_acid_type to be considered for the transfer (either DNA or RNA, Default: ALL)."
    echo " -l <lane>                        Lane(s) to be transferred."
    echo " -s <sample>                      Sample Name(s) (as they appear in the json file from Freezeman) (default: all)."
    echo " -x <xsample>                     Sample Name(s) to be EXCLUDED (as they appear in the json file from Freezeman) (default: none)."
    exit 1                         
}

destination="c3g-data-repos"

while getopts 'hr:d::n::l::s::x:' OPTION; do
  case "$OPTION" in
      r)
          runfolder="$OPTARG"
          ;;
      d)
          destination="$OPTARG"
          ;;
      n)
          nucleic_acid_type="$OPTARG"
          ;;
      l)
          lane+=("$OPTARG")
          ;;
      s)
          sample+=("$OPTARG")
          ;;
      x)
          xsample+=("$OPTARG")
          ;;
      h)
          usage
          ;;
      ?)
          usage
          ;;
  esac
done

run_processing2json_args=""
  if declare -p sample >&/dev/null; then
        run_processing2json_args="${run_processing2json_args} -s ${sample[*]}"
    fi
    if declare -p xsample >&/dev/null; then
          run_processing2json_args="${run_processing2json_args} -x ${xsample[*]}"
      fi
transfer_args=""
if declare -p lane >&/dev/null; then
    transfer_args="${transfer_args} -l ${lane[*]}"
fi

export MUGQIC_INSTALL_HOME=/cvmfs/soft.mugqic/CentOS6
module use "$MUGQIC_INSTALL_HOME/modulefiles"

##################################################
# Initialization
module purge
source ~/project_tracking_cli/venv/bin/activate

## Prepare run list
folder_prefix=/nb/Research/freezeman-processing
input=$(find "$folder_prefix"/*/*/ -maxdepth 1 -type d -name "$runfolder")
echo "-> Processing $runfolder..."

TIMESTAMP=$(date +%FT%H.%M.%S)

if [ -s "$input"  ]; then
      run_processing_json=$path/$runfolder.json
    if [ -z "$nucleic_acid_type"  ]; then
        run_processing2json_args="${run_processing2json_args} --nucleic_acid_type ${nucleic_acid_type}"                  
    
    ~/MoH_Phase2_Automation/run_processing/run_processing2json.py $run_processing2json_args --input $input --output $run_processing_json

    ret="$(pt-cli ingest run_processing --input-json $run_processing_json 2>&1 || true)"
    echo -e "$ret" | tee "${run_processing_json/.json/_${TIMESTAMP}_run_processing_ingestion.log}"
    if ! [[ $ret == *"has to be unique"*  ]] && [[ $ret == *"BadRequestError"*  ]]; then
        echo "Run ${$runfolder} already ingested, proceeding to transfer of lane(s) ${lane}."
    fi
else
    echo "--> ERROR: Missing folder $folder_prefix/*/*/$runfolder"
    exit 1
fi

nohup ~/MoH_Phase2_Automation/run_processing/transfer_run_processing2bucket.sh -r "$run_processing_json" -l "$lane" > "${run_processing_json/.json/_${destination}_${TIMESTAMP}_transfer.log}" 2>&1 &
echo "Transfer started towards $destination. See log file ${run_processing_json/.json/_${destination}_${TIMESTAMP}_transfer.log}"

