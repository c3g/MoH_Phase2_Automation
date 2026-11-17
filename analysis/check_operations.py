#!/usr/bin/env python

import argparse
import json
import subprocess
import urllib.parse

class PtCli:
    def __init__(self, project="MOH-Q", url_root="https://project-tracking.c3g-app.dev-sd4h.ca/"):
        self.project = project
        self.base = ["pt-cli", "-q", "--project", project] + (["--url-root", url_root] if url_root else [])

    def run(self, *args):
        result = subprocess.run(self.base + list(args), capture_output=True, text=True)
        if result.returncode:
            sys.exit(f"pt-cli {' '.join(args)} failed ({result.returncode}): {result.stderr.strip()}")
        return result.stdout

    def route(self, path, query=None):
        if query:
            path += "?json=" + urllib.parse.quote(json.dumps(query))
        return json.loads(self.run("route", f"/project/{self.project}/{path}"))["DB_ACTION_OUTPUT"]

def live(rows):
    return [row for row in rows if not row["deleted"] and not row["deprecated"]]

def decide_group(pt, group_name):

    group = live(json.loads(pt.run("sample_group", "list", "--sample_group_name", group_name)))[0] 
    members = live(pt.route("samples", {"sample_name": ",".join(group["sample_name"])}))
    sample_id_list = [str(sample['id']) for sample in members]
    sample_ids = ",".join(sample_id_list)
    readsets = live(pt.route(f"samples/{sample_ids}/readsets"))
    readset_id_list = [str(readset['id']) for readset in readsets]
    readset_ids = ",".join(readset_id_list)
    operations = [op for op in live(pt.route(f"readsets/{readset_ids}/operations")) if op["analysis"] and op["name"] == "oncoanalyser"]
    print(operations)
    if any(op["status"] in ("PENDING", "RUNNING") for op in operations):
        return {"group": group["name"], "decision": "WAIT", "reason": "an oncoanalyser run of this group is still running: re-check when it ends"}
    complete_overlap = [op for op in operations if set(readset_id_list) <= set(op["readset_ids"])]
    if any(op["status"] == "COMPLETED" for op in complete_overlap):
        return {"group": group["name"], "decision": "SKIP", "reason": "a completed oncoanalyser run already covers all of the group's readsets"}
    else:
        return {"group": group["name"], "decision": "GO", "reason": "analysis not yet successfully completed"}

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-g", "--group", required=True, help="Group to check")
    args = parser.parse_args()

    pt = PtCli()
    print(json.dumps(decide_group(pt, args.group)))

if __name__ == "__main__":
    main()
