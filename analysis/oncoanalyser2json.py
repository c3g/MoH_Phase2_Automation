#!/usr/bin/env python3

### WORK IN PROGRESS ###

import argparse
import glob
import json
import os
import logging
import configparser

logging.basicConfig(format='%(levelname)s: %(asctime)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog='oncoanalyser2json.py',
        description="Creates json file for project tracking database from launch of oncoanalyser analysis."
        )
    parser.add_argument(
        '-i',
        '--input',
        required=True,
        help="Folder of the analysis to be parsed."
        )
    parser.add_argument(
        '-t',
        '--timestamp',
        required=True,
        help="Timestamp of launch to be parsed."
            )
    parser.add_argument(
        '-g',
        '--group',
        required=True,
        help="Group for which to parse analysis."
            )
    parser.add_argument(
        '-o',
        '--output',
        default=None,
        help="Output json filename (Default: .json)."
        )
    return parser.parse_args()

def load_json_file(file_path):
    """Load a JSON file."""
    try:
        with open(file_path, mode="r") as file:
            return json.load(file)
    except FileNotFoundError:
        logger.error(f"JSON file not found: {file_path}")
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON file: {file_path}")
    return None

def parse_samplesheet(samplesheet):
    """
    Parse samplesheet for oncoanalyser run for samples and readsets.
    """
    samples = {}

    with open(samplesheet, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            sample = row["sample_id"]
            info = dict(part.split(":", 1) for part in row["info"].split(";") if ":" in part)
            readset = info.get("library_id") 

            if sample not in samples.keys():
                samples[sample] = [readset]
            else:
                samples[sample].append(readset)

    return samples

### TO MODIFY FOR ONCOANALYSER ###
def create(json_file, sample):
    """
    Starts creating the json dump for the passed sample
    """
    # Run only if json doesn't already exist and oncoanaluser hasn't started running yet? 
    # If oncoanalyser already running/finished, call oncoanalyser_metrics_tracking.py instead
    log.debug(f"Updating project_tracking JSON {json_file} for sample '{sample.name}'")

    with open(json_file, 'r') as j_file:
        current_json_hash = json.load(j_file)

    # Existing sample in json
    sample_hash_position = [pos for pos, val in enumerate(current_json_hash['sample']) if val['sample_name'] == sample]
    if not sample_hash_position:
        sample_json = {
            'sample_name': sample,
            'readset': []
            }
        current_json_hash['sample'].append(sample_json)
    else:
        sample_json = current_json_hash['sample'][sample_hash_position[0]]

    for readset in readsets:
        readset_hash_position = [pos for pos, val in enumerate(sample_json['readset']) if val['readset_name'] == readset]
        if not readset_hash_position:
            readset_json = {
                'readset_name': readset,
                'job': []
                }
            sample_json['readset'].append(readset_json)
        else:
            readset_json = sample_json['readset'][readset_hash_position[0]]
       
       # add something here that calls oncoanalyser_metrics_tracking.py if oncoanalyser is already running or has finished
        if oncoanalyser_done:
            call oncoanalyser_metrics_tracking.py instead
        else:
            job_json = {
                'job_name': f"oncoanalyser.{args.group}",
                'job_start': None,
                'job_stop': None,
                'job_status': None,
                    }
            readset_json['job'].append(job_json)

    with open(json_file, 'w', encoding='utf-8') as j_file:
        json.dump(current_json_hash, j_file, ensure_ascii=False, indent=4)

    return json_file

def init(
    operation_name,
    operation_pipeline,
    operation_config_version,
    operation_cmd_line,
    operation_config_md5sum,
    operation_config_data,
    pipeline_output_dir,
    timestamp
    ):
    """
    Initializes the json for project_tracking database
    """

    json_output = {
        'project_name': "MOH-Q",
        'operation_config_name': 'oncoanalyser_ini',
        'operation_config_version': operation_config_version, # parse from somewhere
        'operation_config_md5sum': operation_config_md5sum, # calculate from merged configs
        'operation_config_data': ''.join(operation_config_data), # parse from somewhere
        'operation_platform': 'cardinal', # better if parsed from somewhere
        'operation_cmd_line': operation_cmd_line, # parse from submission script
        'operation_name': "oncoanalyser",
        'operation_pipeline': operation_pipeline, # parse from submission script
        'sample': []
    }

    json_file = os.path.join(json_folder, f"{operation_name}_{timestamp}.json")
    log.debug(f"Initializing project_tracking JSON: {json_file}")
    with open(json_file, 'w', encoding='utf-8') as j_file:
        json.dump(json_output, j_file, ensure_ascii=False, indent=4)

    return json_file

def main():
    """ Main """
    args = parse_arguments()

    output = args.output or f"{os.path.basename(args.input)}.oncoanalyser.json"

    # only parse submit script and config files if output json doesn't already exist
    submit_script = os.path.join(args.input, f"{args.group}.oncoanalyser.{args.timestamp}.submit"))
    full_command, config_files = parse_submit_script(submit_script)

    # parse used config files from the submission script and convert them to json format (nextflow -c /cvmfs/soft.mugqic/CentOS6/software/oncoanalyser/oncoanalyser-3.0.0/config/onco.config config -o json > onco_config.json)
    # merge the json files and write a single config trace file (python deep merge)
    # calculate md5sum of merged config file and add to json
    init_json()
    # if output json already exists, skip parsing of submit scriot, go to here:
    samplesheet = os.path.join(args.input, "samplesheets", args.timestamp, f"{os.path.basename(input)}.samplesheet.csv"))
    samples = parse_samplesheet(samplesheet)

    #pseudocode for now
    for sample in samples:
        readsets = sample.values()
        create(output, sample, readsets)

