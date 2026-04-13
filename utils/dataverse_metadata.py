"""
dataverse_metadata.py
=====================
Download dataset metadata from any Dataverse installation via its REST API.

Workflows provided
------------------
1. search_datasets()        – paginated Search API → summary metadata list
2. fetch_full_metadata()    – Native API → full JSON for a single dataset (by DOI/PID)
3. export_metadata()        – Export API → full metadata in various standard formats
4. bulk_metadata_to_csv()   – combines (1) + (2) to harvest all datasets into a CSV

Usage (CLI examples)
--------------------
  # List summary metadata of all published datasets, save to CSV
  python dataverse_metadata.py \
      --base-url https://demo.dataverse.org \
      --output datasets_metadata.csv

  # Same but filtered to one dataverse collection, with an API token
  python dataverse_metadata.py \
      --base-url https://dataverse.harvard.edu \
      --api-token YOUR_TOKEN_HERE \
      --subtree archaeology \
      --output arch_datasets.csv

  # Export full metadata for one dataset as JSON
  python dataverse_metadata.py \
      --base-url https://demo.dataverse.org \
      --export doi:10.70122/FK2/XXXXX \
      --format dataverse_json \
      --output single_dataset.json

Dependencies
------------
  pip install requests tqdm pandas
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Generator, Optional

import requests
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Low-level HTTP helper
# ─────────────────────────────────────────────────────────────────────────────

class DataverseClient:
    """Thin wrapper around `requests` for Dataverse REST endpoints."""

    EXPORT_FORMATS = [
        "dataverse_json",   # most complete, Dataverse-native
        "schema.org",       # JSON-LD
        "OAI_ORE",
        "Datacite",
        "oai_datacite",
        "oai_dc",
        "dcterms",
    ]

    def __init__(
        self,
        base_url: str,
        api_token: Optional[str] = None,
        timeout: int = 30,
        retry_delay: float = 2.0,
        max_retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retry_delay = retry_delay
        self.max_retries = max_retries
        self.session = requests.Session()
        if api_token:
            self.session.headers.update({"X-Dataverse-key": api_token})

    def get(self, endpoint: str, params: dict | None = None) -> dict:
        """GET request with basic retry logic."""
        url = f"{self.base_url}{endpoint}"
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
            except requests.HTTPError as exc:
                log.warning("HTTP %s on %s (attempt %d/%d)", exc.response.status_code, url, attempt, self.max_retries)
                if exc.response.status_code in {429, 503}:
                    time.sleep(self.retry_delay * attempt)
                else:
                    raise
            except requests.RequestException as exc:
                log.warning("Request error: %s (attempt %d/%d)", exc, attempt, self.max_retries)
                time.sleep(self.retry_delay * attempt)
        raise RuntimeError(f"Failed to GET {url} after {self.max_retries} retries")

    def get_raw(self, endpoint: str, params: dict | None = None) -> bytes:
        """GET request returning raw bytes (for non-JSON export formats)."""
        url = f"{self.base_url}{endpoint}"
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.content


# ─────────────────────────────────────────────────────────────────────────────
# 1. Search API – paginated list of all published datasets
# ─────────────────────────────────────────────────────────────────────────────

def search_datasets(
    client: DataverseClient,
    query: str = "*",
    subtree: Optional[str] = None,
    per_page: int = 1000,
    metadata_fields: Optional[list[str]] = None,
) -> Generator[dict[str, Any], None, None]:
    """
    Yield one dict per published dataset via the Dataverse Search API.

    Parameters
    ----------
    client:
        Authenticated DataverseClient instance.
    query:
        Solr query string; "*" returns everything.
    subtree:
        Alias of a dataverse collection to restrict the search to.
    per_page:
        Results per API call (max 1000).
    metadata_fields:
        Extra metadata block fields to include, e.g. ["citation:author",
        "citation:*", "geospatial:*"].  Requires Dataverse ≥ 5.10.
    """
    params: dict[str, Any] = {
        "q": query,
        "type": "dataset",
        "per_page": per_page,
        "start": 0,
        "sort": "date",
        "order": "asc",
    }
    if subtree:
        params["subtree"] = subtree

    # metadata_fields is a repeated parameter; requests handles list values
    if metadata_fields:
        params["metadata_fields"] = metadata_fields

    total: Optional[int] = None
    fetched = 0

    with tqdm(desc="Searching datasets", unit=" datasets", total=None) as bar:
        while True:
            data = client.get("/api/search", params=params)
            items = data["data"]["items"]
            if total is None:
                total = data["data"]["total_count"]
                bar.total = total
                log.info("Total published datasets found: %d", total)

            for item in items:
                yield item
                fetched += 1
                bar.update(1)

            params["start"] += per_page
            if params["start"] >= total:
                break

            # Be polite to the server
            time.sleep(0.1)

    log.info("Search complete: %d datasets retrieved", fetched)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Native API – full metadata for a single dataset
# ─────────────────────────────────────────────────────────────────────────────

def fetch_full_metadata(
    client: DataverseClient,
    pid: str,
    version: str = ":latest-published",
) -> dict[str, Any]:
    """
    Return the full native-JSON metadata for a dataset identified by its
    persistent identifier (DOI or Handle).

    Parameters
    ----------
    pid:
        Persistent identifier, e.g. "doi:10.7910/DVN/ABC123".
    version:
        Dataset version string.  Special values: ":latest", ":latest-published",
        ":draft".  Numeric versions are "1.0", "2.1", etc.
    """
    data = client.get(
        f"/api/datasets/:persistentId/versions/{version}",
        params={"persistentId": pid},
    )
    return data["data"]


def extract_citation_fields(full_meta: dict[str, Any]) -> dict[str, Any]:
    """
    Flatten the most useful citation fields from a native-JSON metadata block
    into a simple key→value dictionary suitable for CSV export.
    """
    blocks = full_meta.get("metadataBlocks", {})
    citation = blocks.get("citation", {}).get("fields", [])

    flat: dict[str, Any] = {
        "datasetVersion": full_meta.get("versionNumber"),
        "versionState": full_meta.get("versionState"),
        "createTime": full_meta.get("createTime"),
        "lastUpdateTime": full_meta.get("lastUpdateTime"),
    }

    # Map typeName → value (handles both primitive and compound fields)
    for field in citation:
        name = field["typeName"]
        multiple = field.get("multiple", False)
        value = field.get("value")

        if name == "author" and isinstance(value, list):
            flat["authors"] = "; ".join(
                a.get("authorName", {}).get("value", "") for a in value
            )
        elif name == "datasetContact" and isinstance(value, list):
            flat["contacts"] = "; ".join(
                c.get("datasetContactEmail", {}).get("value", "") for c in value
            )
        elif name == "dsDescription" and isinstance(value, list):
            flat["description"] = " | ".join(
                d.get("dsDescriptionValue", {}).get("value", "") for d in value
            )
        elif name == "subject" and isinstance(value, list):
            flat["subjects"] = "; ".join(value)
        elif name == "keyword" and isinstance(value, list):
            flat["keywords"] = "; ".join(
                k.get("keywordValue", {}).get("value", "") for k in value
            )
        elif multiple and isinstance(value, list):
            flat[name] = "; ".join(str(v) for v in value)
        else:
            flat[name] = value

    return flat


# ─────────────────────────────────────────────────────────────────────────────
# 3. Export API – single dataset, standard formats (dataverse_json, datacite…)
# ─────────────────────────────────────────────────────────────────────────────

def export_metadata(
    client: DataverseClient,
    pid: str,
    export_format: str = "dataverse_json",
) -> bytes:
    """
    Export the current published version of a dataset in the requested format.

    Supported formats (client.EXPORT_FORMATS):
        dataverse_json, schema.org, OAI_ORE, Datacite, oai_datacite, oai_dc, dcterms

    Returns raw bytes so the caller can write JSON, XML, or any other format.
    """
    if export_format not in DataverseClient.EXPORT_FORMATS:
        log.warning(
            "Unknown export format '%s'. Known formats: %s",
            export_format,
            DataverseClient.EXPORT_FORMATS,
        )
    return client.get_raw(
        "/api/datasets/export",
        params={"exporter": export_format, "persistentId": pid},
    )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Bulk harvest: Search → full metadata → CSV
# ─────────────────────────────────────────────────────────────────────────────

# Columns always written to the CSV from the Search API response
SEARCH_COLUMNS = [
    "name",
    "global_id",
    "description",
    "url",
    "published_at",
    "citationHtml",
    "publisher",
    "subjects",
    "fileCount",
    "versionId",
    "versionState",
]

def bulk_metadata_to_csv(
    client: DataverseClient,
    output_path: Path,
    query: str = "*",
    subtree: Optional[str] = None,
    fetch_full: bool = False,
    metadata_fields: Optional[list[str]] = None,
) -> int:
    """
    Harvest metadata for all published datasets and write to a CSV file.

    Parameters
    ----------
    fetch_full:
        If True, an additional Native API call is made for every dataset to
        retrieve the full citation metadata.  This is slower but produces richer
        output.  If False, only the fields returned by the Search API are saved.

    Returns
    -------
    int
        Number of datasets written.
    """
    first_row = True
    writer: Optional[csv.DictWriter] = None
    fh = None
    count = 0

    try:
        fh = open(output_path, "w", newline="", encoding="utf-8")

        for item in search_datasets(
            client,
            query=query,
            subtree=subtree,
            metadata_fields=metadata_fields or ["citation:*"],
        ):
            row: dict[str, Any] = {col: item.get(col, "") for col in SEARCH_COLUMNS}

            # Optionally enrich with full Native API metadata
            if fetch_full:
                pid = item.get("global_id")
                if pid:
                    try:
                        full = fetch_full_metadata(client, pid)
                        extra = extract_citation_fields(full)
                        row.update(extra)
                    except Exception as exc:
                        log.warning("Could not fetch full metadata for %s: %s", pid, exc)

            if first_row:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=list(row.keys()),
                    extrasaction="ignore",
                    lineterminator="\n",
                )
                writer.writeheader()
                first_row = False

            writer.writerow(row)
            count += 1

    finally:
        if fh:
            fh.close()

    log.info("Wrote %d datasets to %s", count, output_path)
    return count


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Download dataset metadata from a Dataverse installation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--base-url",
        default="https://demo.dataverse.org",
        help="Base URL of the Dataverse instance (default: demo.dataverse.org).",
    )
    p.add_argument(
        "--api-token",
        default=None,
        help="API token (required for private/draft datasets).",
    )
    p.add_argument(
        "--output",
        default="datasets_metadata.csv",
        help="Output file path (CSV for bulk mode, JSON/XML for single export).",
    )
    p.add_argument(
        "--subtree",
        default=None,
        help="Limit search to a specific dataverse collection alias.",
    )
    p.add_argument(
        "--query",
        default="*",
        help="Solr query string (default: '*' = all datasets).",
    )
    p.add_argument(
        "--fetch-full",
        action="store_true",
        help="Fetch full Native API metadata per dataset (slower, richer output).",
    )
    p.add_argument(
        "--export",
        metavar="PID",
        default=None,
        help="Export metadata of a single dataset by its PID (e.g. doi:10.7910/…).",
    )
    p.add_argument(
        "--format",
        default="dataverse_json",
        choices=DataverseClient.EXPORT_FORMATS,
        help="Export format for --export mode (default: dataverse_json).",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    client = DataverseClient(base_url=args.base_url, api_token=args.api_token)

    # ── Mode A: single-dataset export ────────────────────────────────────────
    if args.export:
        log.info("Exporting metadata for %s as %s …", args.export, args.format)
        raw = export_metadata(client, pid=args.export, export_format=args.format)
        output = Path(args.output)
        output.write_bytes(raw)
        log.info("Saved to %s (%d bytes)", output, len(raw))
        return

    # ── Mode B: bulk CSV harvest ──────────────────────────────────────────────
    log.info(
        "Harvesting metadata from %s (subtree=%s, fetch_full=%s) …",
        args.base_url,
        args.subtree or "root",
        args.fetch_full,
    )
    n = bulk_metadata_to_csv(
        client,
        output_path=Path(args.output),
        query=args.query,
        subtree=args.subtree,
        fetch_full=args.fetch_full,
    )
    print(f"\n✓ Done — {n} datasets written to {args.output}")


if __name__ == "__main__":
    main()
