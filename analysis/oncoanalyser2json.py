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
    "TBD"

    return samples

### TO MODIFY FOR ONCOANALYSER ###
def create(pipeline, sample):
    """
    Starts creating the json dump for the passed sample
    """

    json_folder = os.path.join(pipeline.output_dir, "json")
    try:
        json_file = os.path.join(json_folder, f"{pipeline.__class__.__name__}.{pipeline.protocol}_{pipeline.timestamp}.json")
    except AttributeError:
        json_file = os.path.join(json_folder, f"{pipeline.__class__.__name__}_{pipeline.timestamp}.json")

    if not os.path.isabs(pipeline.output_dir):
        pipeline_output_dir = os.path.abspath(pipeline.output_dir)
    else:
        pipeline_output_dir = pipeline.output_dir
    # /!\ Can't os.path.join otherwise the 'server://' disappears
    cluster_server = global_conf.global_get("DEFAULT", 'cluster_server', required=True)
    path_prefix = f"{cluster_server}://{pipeline_output_dir}"

    log.debug(f"Updating project_tracking JSON {json_file} for sample '{sample.name}'")

    with open(json_file, 'r') as j_file:
        current_json_hash = json.load(j_file)

    # Existing sample in json
    sample_hash_position = [pos for pos, val in enumerate(current_json_hash['sample']) if val['sample_name'] == sample.name]
    if not sample_hash_position:
        sample_json = {
            'sample_name': sample.name,
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
        
        # append jobs only if oncoanalyser has already run
        # if oncoanalyser hasn't launched yet, only append orchestrator job (minimum requirement for ingesting analysis json)

        if oncoanalyser_done: #TBD mechanism
            for job in step.jobs:
                if readset in job.readsets:
                    job_hash_position = [pos for pos, val in enumerate(readset_json['job']) if val['job_name'] == job.name]
                    if not job_hash_position:
                        job_json = {
                            'job_name': job.name,
                            'job_start': None,
                            'job_stop': None,
                            'job_status': None,
                            'file': []
                            }
                        readset_json['job'].append(job_json)
                    else:
                        job_json = readset_json['job'][job_hash_position[0]]
                    for output_file in job.output_files:
                        file_hash_position = [pos for pos, val in enumerate(job_json['file']) if val['file_name'] == os.path.basename(output_file)]
                        if not file_hash_position:
                            # /!\ Can't os.path.join for location_uri otherwise the 'server://' disappears
                            _, extension = os.path.splitext(os.path.basename(output_file))
                            if extension:

                                if "://" in output_file:
                                    location_uri = output_file

                                else:
                                    output_file_norm = os.path.normpath(output_file)
                                    pipeline_output_norm = os.path.normpath(pipeline_output_dir)

                                    if os.path.isabs(output_file_norm):
                                        if output_file_norm.startswith(pipeline_output_norm + os.sep):
                                            relative = os.path.relpath(output_file_norm, pipeline_output_norm)
                                            location_uri = f"{cluster_server}://{pipeline_output_norm}/{relative}"
                                        else:
                                            location_uri = f"{cluster_server}://{output_file_norm}"
                                    else:
                                        location_uri = f"{path_prefix.rstrip('/')}/{output_file_norm.lstrip('/')}"

                                file_json = {
                                    'location_uri': location_uri,
                                    'file_name': os.path.basename(output_file),
                                    'file_md5sum': None
                                    }
                                job_json['file'].append(file_json)
                        else:
                            file_json = job_json['file'][file_hash_position[0]]
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

    json_folder = os.path.join(pipeline_output_dir, "json")

    if not os.path.exists(json_folder):
        os.makedirs(json_folder)

    json_file = os.path.join(json_folder, f"{operation_name}_{timestamp}.json")
    log.debug(f"Initializing project_tracking JSON: {json_file}")
    with open(json_file, 'w', encoding='utf-8') as j_file:
        json.dump(json_output, j_file, ensure_ascii=False, indent=4)

    return json_file

def main():
    """ Main """
    args = parse_arguments()

    output = args.output or f"{os.path.basename(args.input)}.oncoanalyser.json"

    samplesheet = os.path.join(args.input, "samplesheets", args.timestamp, f"{os.path.basename(input)}.samplesheet.csv"))
    samples = parse_samplesheet(samplesheet)

    submit_script = os.path.join(args.input, f"{args.group}.oncoanalyser.{args.timestamp}.submit"))
    full_command, config_files = parse_submit_script(submit_script)

    # parse used config files from the submission script and convert them to json format (nextflow -c /cvmfs/soft.mugqic/CentOS6/software/oncoanalyser/oncoanalyser-3.0.0/config/onco.config config -o json > onco_config.json)
    # merge the json files and write a single config trace file (python deep merge)
    # calculate md5sum of merged config file and add to json

    init_json()

