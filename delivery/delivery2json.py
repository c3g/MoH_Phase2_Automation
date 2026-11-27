#!/usr/bin/env python3

import argparse
import glob
import json
import os
import logging

logging.basicConfig(format='%(levelname)s: %(asctime)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

SRC_BASE_PATH = "/project/60007/MOH_PHASE2/MAIN" 
DEST_BASE_PATH = "/MOH-Q"

def main():
    """ Main  """
    parser = argparse.ArgumentParser(prog='delivery2json.py', description="Creates json file for project tracking database for a given delivery of data.")
    parser.add_argument('-i', '--input', required=True, help="Globus list of transferred files (globus task show --successful-transfers -F json).")
    parser.add_argument('-r', '--run_dir', required=True, help="Run folder of the analysis (holds the oncoanalyser json).")
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
            transferred_json = args.input,
            run_dir = args.run_dir,
            source = args.source,
            destination = args.destination.lower(),
            output = output,
            operation_cmd_line = args.operation_cmd_line,
            start = args.start,
            stop = args.stop
            )

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

def readsets_by_uri(run_dir):
    """location_uri -> [readset names], from the run's analysis json (= what was ingested in the DB)"""
    group = os.path.basename(run_dir)
    analysis_json = sorted(glob.glob(os.path.join(run_dir, f"{group}.oncoanalyser.*.json")))[-1]
    with open(analysis_json, encoding='utf-8') as aj:
        analysis = json.load(aj)

    mapping = {}
    for sample in analysis["sample"]:
        for readset in sample["readset"]:
            for job in readset["job"]:
                for file_entry in job.get("file", []):
                    names = mapping.setdefault(file_entry["location_uri"], []) # sets readsets linked to the file
                    if readset["readset_name"] not in names:
                        names.append(readset["readset_name"])
    return mapping

def jsonify_delivery_transfer(transferred_json, run_dir, source, destination, output, operation_cmd_line, start=None, stop=None):    
    """Writing delivery json: one entry per file Globus copied that is tracked in the DB"""

    start = start.replace('.', ':').replace('T', ' ') if start else None
    stop = stop.replace('.', ':').replace('T', ' ') if stop else None

    json_output = {
            "operation_platform": source,
            "operation_cmd_line": operation_cmd_line,
            "job_start": start,
            "job_stop": stop,
            "readset": []
            }


    # map all files to readsets from the run's analysis json
    readsets_of = readsets_by_uri(run_dir)

    # read full file list fron globus
    with open(transferred_json, encoding='utf-8') as tj:
        transferred = json.load(tj)
    records = transferred.get("DATA", []) if isinstance(transferred, dict) else transferred
    if not records:
        raise RuntimeError(f"No transferred file in {transferred_json}: nothing to ingest")


    for record in records:
        src_path = SRC_BASE_PATH + "/" + record["source_path"].lstrip("/")
        dest_path = record["destination_path"].replace("/~/", "/").lstrip("/")
        src_location_uri = f"{source}://{src_path}"                            # cardinal:///project/.../results/purple/x.tsv
        dest_location_uri = f"{destination}://{DEST_BASE_PATH}/{dest_path}"     # c3g-data-repos:///MOH-Q/<inst>/.../results/purple/x.tsv

        readset_names = readsets_of.get(src_location_uri)
        if not readset_names:
            logger.info(f"Not tracked in the DB, skipped: {src_path}")   # e.g. pipeline_info/*
            continue
        for readset_name in readset_names:
            _append_file(json_output, readset_name, src_location_uri, dest_location_uri)

    if not json_output["readset"]:
        raise RuntimeError("None of the transferred files is tracked in the DB: nothing to ingest")

    with open(output, 'w', encoding='utf-8') as file:
        json.dump(json_output, file, ensure_ascii=False, indent=4)


if __name__ == '__main__':
    main()