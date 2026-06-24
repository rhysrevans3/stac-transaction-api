import os
import json
import argparse
import random
from urllib import parse as urlparse
from stac_client import TransactionClient


def main(args):
    tc = TransactionClient(stac_api=args.stac_transaction_api)
    region = "East" if args.east else "West"

    start_index = args.dc * 500 % 2000 + 1
    end_index = start_index % 2000 + 499
    with open(f"{region}-CMIP6-paths-{start_index:04d}-{end_index:04d}.txt", "r") as f:
        paths = f.readlines()
        print(len(paths), f"paths found for Data Challenge {args.dc}")

    if args.dc == 4:
        for i, path in enumerate(paths):
            path = path.strip()
            item_id = path.replace("/", ".")
            file_name = path.replace("/", ".") + ".json"
            file_path = os.path.join(args.payloads_dir, file_name)

            if not os.path.exists(file_path):
                print(f"File {file_path} does not exist. Skipping.")
                continue
            print(f"POSTing {path} to {region} STAC Transaction API")
            with open(file_path, "r") as f:
                entry = json.load(f)
                print(f"Entry: {entry}")
                # Change value type of random properties
                if i > 400:
                    random_key = random.choice(list(entry.get("properties").keys()))
                    if isinstance(entry.get("properties").get(random_key), str):
                        entry["properties"][random_key] = 5.4
                    else:
                        entry["properties"][random_key] = "test_value"
                response = tc.post(entry)
                print(f"Response: {response}")

        for i, path in enumerate(paths):
            path = path.strip()
            item_id = path.replace("/", ".")

            if not os.path.exists(file_path):
                print(f"File {file_path} does not exist. Skipping.")
                continue

            print(f"PATCHing {path} to {region} STAC Transaction API")
            # Retraction
            if 100 < i and i <= 200:
                operations = [{"op": "add", "path": "/properties/retracted", "value": True}]
                response = tc.json_patch(
                    "CMIP6",
                    item_id=item_id,
                    entry={"operations": operations},
                )
                print(f"Response: {response}")

            # Replication
            elif i <= 300:
                with open(file_path, "r") as f:
                    entry = json.load(f)
                    assets = entry.get("assets", {})
                    operations = []
                    for key, value in assets.items():
                        href = value.get("href", "")
                        href_parsed = urlparse.urlparse(href)
                        type = value.get("type", "")
                        roles = value.get("roles", [])
                        description = value.get("description", "")
                        entry = {
                            "op": "add",
                            "path": f"/assets/{key}",
                            "value": {
                                "alternate": {
                                    "eagle.alcf.anl.gov": {
                                        "href": f"{href_parsed.scheme}://eagle.alcf.anl.gov{href_parsed.path}",
                                        "type": type,
                                        "roles": roles,
                                        "description": description,
                                        "alternate:name": "eagle.alcf.anl.gov",
                                    }
                                },
                            },
                        }
                        operations.append(entry)
                    response = tc.json_patch("CMIP6", item_id=item_id, entry={"operations": operations})
                    print(f"Response: {response}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="STAC Transaction API Data Challenges")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--east", action="store_true", help="Test East STAC Transaction API")
    group.add_argument("--west", action="store_true", help="Test West STAC Transaction API")
    parser.add_argument("--stac-transaction-api", type=str, help="URL to STAC Transaction API")
    parser.add_argument("--dc", type=int, choices=[1, 2, 3, 4, 5], required=True, help="Data Challenge (1-5)")
    parser.add_argument(
        "--payloads-dir",
        type=str,
        default="esgfng-payloads",
        help="A directory where files with ESGF-NG payloads will be stored.",
    )
    args = parser.parse_args()

    main(args)
