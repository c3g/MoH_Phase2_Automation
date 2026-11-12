#!/usr/bin/env python3

### WORK IN PROGRESS ###

import argparse
import csv
import hashlib
import json
import os
import logging
import oncoanalyser_metrics_tracking
import subprocess

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
            if row["sample_type"] == "tumor" and row["sequence_type"] == "dna":
                tumor_dna = sample

            if sample not in samples.keys():
                samples[sample] = [readset]
            else:
                samples[sample].append(readset)

    return samples, tumor_dna

def parse_submit_script(submit_script_filename):
    """
    Parse the oncoanalyser submission script for the full command and configs used.
    """

    with open(submit_script_filename, 'r') as submit_script:
        single_line = submit_script.read().replace("\\\n", " ")

        for line in single_line.splitlines():
            commands = line.split()
            # Find "nextflow run" command and following
            for i in range(len(commands) - 1):
                if commands[i] == "module" and commands[i + 1] == "load":
                    version = commands[i + 2].split("/")[2]
                if commands[i] == "nextflow" and commands[i + 1] == "run":
                    onco_cmd = commands[i:]
                    break
    configs = []
    for i, cmd in enumerate(onco_cmd[:-1]):
        if cmd in ("-c", "-config"):
            configs.extend(p for p in onco_cmd[i + 1].split(",") if p)

    full_command = " ".join(onco_cmd)
    
    return full_command, version, configs

def parse_config_files(config_files, config_trace_filename):
    """
    Look for config trace file, create if not found.
    """

    if not os.path.isfile(config_trace_filename):
        merge_config_files(config_files, config_trace_filename)

    config_trace_content = []
    with open(config_trace_filename, 'r') as config_trace:
        for line in config_trace:
            config_trace_content.append(line)

    return config_trace_content

def merge_config_files(config_files, config_trace_filename):
    """
    Merge nextflow config files into a single trace config.
    """
    cmd = ["module", "purge", "&&", "module", "load", "mugqic/oncoanalyser/3.0.0", "&&", "nextflow", "-q"]

    for config in config_files:
        cmd += ["-c", str(config)]
    cmd.append("config")
    cmd.append("-show-profiles")
    cmd.append(">")
    cmd.append(config_trace_filename)

    result = subprocess.run(
            " ".join(cmd),
            cwd=os.path.dirname(config_trace_filename),
            shell=True,
            capture_output=True,
            text=True,
            check=False,
            timeout=120
            )

    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to create config trace file:\n{result.stderr}"
            )

def md5_list(content_list):
    """
    Returns md5 of the content of a list
    """
    hash_md5 = hashlib.md5()

    for item in content_list:
        hash_md5.update(item.encode('utf-8'))
    
    return hash_md5.hexdigest()

### TO MODIFY FOR ONCOANALYSER ###
def create(json_file, group, sample, readsets, timestamp, tumor_dna):
    """
    Starts creating the json dump for the passed sample
    """
    # Run only if json doesn't already exist and oncoanaluser hasn't started running yet? 
    # If oncoanalyser already running/finished, call oncoanalyser_metrics_tracking.py instead
    logger.debug(f"Updating project_tracking JSON {json_file} for sample '{sample}'")

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
       # 
        oncoanalyser_slurm = os.path.join(args.input, f"{group}.oncoanalyser_{timestamp}.out")
        if os.path.isfile(oncoanalyser_slurm):
            oncoanalyser_metrics_tracking.jsonify_oncoanalyser_metrics(
                    input=args.input, 
                    group=group, 
                    results_dir=os.path.join(args.input, "results"), 
                    output_json=json_file, 
                    readset=readset, 
                    sample_id=sample, 
                    tumor_dna=tumor_dna)
        else:
            job_json = {
                'job_name': f"oncoanalyser.{group}",
                'job_start': None,
                'job_stop': None,
                'job_status': "PENDING",
                    }
            readset_json['job'].append(job_json)

    with open(json_file, 'w', encoding='utf-8') as j_file:
        json.dump(current_json_hash, j_file, ensure_ascii=False, indent=4)

    return json_file

def init_json(
    operation_cmd_line,
    operation_config_version,
    operation_config_files,
    config_trace_filename,
    json_file
    ):
    """
    Initializes the json for project_tracking database
    """

    operation_config_data = parse_config_files(operation_config_files, config_trace_filename)

    json_output = {
        'project_name': "MOH-Q",
        'operation_config_name': 'oncoanalyser_ini',
        'operation_config_version': operation_config_version, 
        'operation_config_md5sum': md5_list(operation_config_data),
        'operation_config_data': ''.join(operation_config_data), # parse from somewhere
        'operation_platform': 'cardinal', # better if parsed from somewhere
        'operation_cmd_line': operation_cmd_line,
        'operation_name': "oncoanalyser",
        'operation_pipeline': "wgts",
        'sample': []
    }

    logger.debug(f"Initializing project_tracking JSON: {json_file}")
    with open(json_file, 'w', encoding='utf-8') as j_file:
        json.dump(json_output, j_file, ensure_ascii=False, indent=4)

    return json_file

def main():
    """ Main """
    args = parse_arguments()

    output = args.output or os.path.join(args.input, f"{args.group}.oncoanalyser.{args.timestamp}.json")
    json_file = os.path.join(args.input, output)
    if not os.path.isfile(os.path.join(json_file)):
        # only parse submit script and config files if output json doesn't already exist
        submit_script = os.path.join(args.input, f"{args.group}.oncoanalyser_{args.timestamp}.submit")
        full_command, version, config_files = parse_submit_script(submit_script)

        config_trace_filename = os.path.join(args.input, f"Oncoanalyser_{args.timestamp}.trace.config")
        init_json(full_command, version, config_files, config_trace_filename, json_file)
    
    # if output json already exists, skip parsing of submit scriot, go to here:
    samplesheet = os.path.join(args.input, "samplesheets", args.timestamp, f"{args.group}.samplesheet.csv")
    samples, tumor_dna = parse_samplesheet(samplesheet)

    # add or update entries
    for sample, readsets in samples.items():
        create(json_file, args.group, sample, readsets, args.timestamp, tumor_dna)

if __name__ == '__main__':
    main()
