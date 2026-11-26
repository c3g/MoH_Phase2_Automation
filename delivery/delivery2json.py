#!/usr/bin/env python3

import argparse
import glob
import json
import os
import logging

logging.basicConfig(format='%(levelname)s: %(asctime)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """ Main  """
    parser = argparse.ArgumentParser(prog='delivery2json.py', description="Creates json file for project tracking database for a given delivery of data.")
    parser.add_argument('-i', '--input', required=True, help="Batch file from Globus.")
    parser.add_argument('-s', '--source', required=True, help="Source cluster of the transfer.")
    parser.add_argument('-d', '--destination', required=True, help="Bucket of destination for the transfer.")
    parser.add_argument('-o', '--output', required=False, help="Output json filename (Default: <input_filename>.json).")
    parser.add_argument('--start', required=False, help="Start time of operation (format: YYYY-MM-DDTHH.MM.SS).")
    parser.add_argument('--stop', required=False, help="End time of operation (format: YYYY-MM-DDTHH.MM.SS).")
    parser.add_argument('--operation_cmd_line', required=True, help="Command used for transfer.")
    args = parser.parse_args()

    if not args.output:
        base_name, _ = os.path.splitext(args.input)
        output = os.path.basename(base_name) + ".json"
    else:
        output = args.output

    jsonify_delivery_transfer(
            batch_file = args.input,
            source = args.source,
            destination = args.destination.lower(),
            output = output,
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


def _append_file(json_output, readset_name, src_location_uri, dest_location_uri):
    """Append a file entry to an existing readset or create a new one."""
    
    for readset in json_output["readset"]:
        if readset["readset_name"] == readset_name:
            readset["file"].append(
                    {
                        "src_location_uri": src_location_uri,
                        "dest_location_uri": dest_location_uri                                                                                
                    }                          
                )
            return
        #Not found: create new
    json_output["readset"].append(
            {
                "readset_name": readset_name,
                "file": [
                    {
                        "src_location_uri": src_location_uri,
                        "dest_location_uri": dest_location_uri
                    }
                ]
            }
        )

def jsonify_delivery_transfer(batch_file, source, destination, output, operation_cmd_line, start=None, stop=None):
    """Writing transfer json based on delivery batch file"""
    
    start = start.replace('.', ':').replace('T', ' ') if start else None
    stop = stop.replace('.', ':').replace('T', ' ') if stop else None

    json_output = {
            "operation_platform": source,
            "operation_cmd_line": operation_cmd_line,
            "job_start": start,
            "job_stop": stop,
            "readset": []                                                                        
            }

    with open(batch_file, 'r') as file:
        for raw_line in file:
            line = raw_line.strip()

            fields = line.split()
            if len(fields) < 2:
                continue # malformed line

            src_path = fields[0]
            dest_path = fields[1]
            
            # Build URIs once
            src_location_uri = f"{source}://{src_path}"
            dest_location_uri = f"{destination}://{dest_path.strip()}"

            run_dir = os.path.dirname(os.path.dirname(src_path))
            group = os.path.basename(os.path.dirname(run_dir))

            samplesheet_candidates = glob.glob(os.path.join(run_dir, "samplesheets", "*", f"{group}.samplesheet.csv"))
            samplesheet_main = max(samplesheet_candidates, key=os.path.getmtime)
            if not samplesheet_main:
                raise FileNotFoundError(f"No main samplesheet found in folder {args.input}")
            samples = parse_samplesheet(samplesheet_main)

            for sample, readsets in samples.items():
                _append_file(json_output, readset, src_location_uri, dest_location_uri)
            
    with open(output, 'w', encoding='utf-8') as file:
        json.dump(json_output, file, ensure_ascii=False, indent=4)


if __name__ == '__main__':
        main()
