#!/usr/bin/env python3

import argparse
import json
import os
import logging

logging.basicConfig(format='%(levelname)s: %(asctime)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """ Main  """
    parser = argparse.ArgumentParser(prog='djerba2json.py', description="Creates json file for project tracking database for a djerba report generation operation.")
    parser.add_argument('-i', '--input', required=True, help="Djerba ini file.")
    parser.add_argument('-o', '--output', required=False, help="Output json filename (Default: <input_filename>.json).")
    parser.add_argument('--start', required=False, help="Start time of operation (format: YYYY-MM-DDTHH.MM.SS).")
    parser.add_argument('--stop', required=False, help="End time of operation (format: YYYY-MM-DDTHH.MM.SS).")
    parser.add_argument('--operation_cmd_line', required=True, help="Command used for transfer.")
    args = parser.parse_args()

    run_dir = os.path.dirname(os.path.dirname(args.input))
    group = os.bath.basename(run_dir)
    
    if not args.output:
        output = os.path.join(run_dir), f"{group}.djerba.json"
    else:
        output = args.output

    jsonify_djerba(
            ini_file = args.input,
            json_file = output,
            run_dir = run_dir,
            group = group,
            operation_cmd_line = args.operation_cmd_line,
            start = args.start,
            stop = args.stop                                                                                                                                    
            )

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
                role = "tumor"
            if row["sequence_type"] == "rna":
                role = "rna"
            if row["sample_type"] == "normal":
                role = "normal"

            if sample not in samples.keys():
                samples[sample] = {"readsets": [readset]}
            else:
                samples[sample]["readsets"].append(readset)
            samples[sample]["role"] = role

    return samples, tumor_dna

def md5_list(content_list):
    """
    Returns md5 of the content of a list
    """
    hash_md5 = hashlib.md5()

    for item in content_list:
        hash_md5.update(item.encode('utf-8'))
    
    return hash_md5.hexdigest()

def create(json_file, group, sample, readsets, start, stop):
    """ Create entries for samples and readsets """
    
    with open(json_file, 'r') as j_file:
        current_json_hash = json.load(j_file)

    run_dir = os.path.dirname(os.path.abspath(json_file))
    djerba_report = os.path.join(run_dir, "results", f"{tumor_dna}_report.research.pdf")

    sample_json = {
        'sample_name': sample,
        'readset': []
        }

    for readset in readsets:
        readset_json = {
            'readset_name': readset,
            'job': [
                {
                    'job_name': f"djerba_report.{group}",
                    'job_start': start,
                    'job_stop': stop,
                    'job_status': "COMPLETED",
                    'file': [
                        {
                            "file_name": "MoHQ-CS-235-2-DT.redux.bam",
                            "location_uri": f"cardinal://{djerba_report}"
                        }
                    ]
                }
            ]
        }
        sample_json['readset'].append(readset_json)

    current_json_hash['sample'].append(sample_json)

    with open(json_file, 'w', encoding='utf-8') as j_file:
        json.dump(current_json_hash, j_file, ensure_ascii=False, indent=4)

def jsonify_djerba(ini_file, json_file, run_dir, group, operation_cmd_line, start=None, stop=None):
    """Writing operation json based on djerba command."""
    start = start.replace('.', ':').replace('T', ' ') if start else None
    stop = stop.replace('.', ':').replace('T', ' ') if stop else None

    operation_config_data = []
    with open(ini_file, 'r') as config_trace:
        for line in config_trace:
            operation_config_data.append(line)
    operation_config_md5sum = md5_list(operation_config_data) 

    json_output = {
            "operation_name": "djerba",
            "operation_pipeline": None,
            "operation_status": "COMPLETED",
            "operation_config_name": os.path.basename(ini_file),
            "operation_config_version": "TBD",
            "operation_config_md5sum": operation_config_md5sum,
            "operation_config_data": ''.join(operation_config_data),
            "operation_platform": "cardinal",
            "operation_cmd_line": operation_cmd_line,
            "sample": []                                                                      
            }

    with open(json_file, 'w', encoding='utf-8') as j_file:
        json.dump(json_output, j_file, ensure_ascii=False, indent=4)
            
    samplesheet_candidates = glob.glob(os.path.join(run_dir, "samplesheets", "*", f"{group}.samplesheet.csv"))
    samplesheet_main = max(samplesheet_candidates, key=os.path.getmtime)
    if not samplesheet_main:
        raise FileNotFoundError(f"No main samplesheet found in folder {args.input}")
    samples, tumor_dna = parse_samplesheet(samplesheet_main)

    for sample, value in samples.items():
        create(json_file, group, sample, value['readsets'], start, stop, tumor_dna)
            
