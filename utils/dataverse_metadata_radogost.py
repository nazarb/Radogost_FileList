"""
dataverse_metadata_radogost.py
==============================
Download dataset metadata from the DARIAH-PL Dataverse installation at
https://radogost.dariah.pl

Target dataset
--------------
  PID:     doi:10.82343/GKBKTC
  Version: DRAFT  (API token required for draft access)

Workflows
---------
1. fetch_draft_metadata()   – full native JSON for the draft version
2. search_datasets()        – paginated Search API → summary list of all
                              published datasets on the instance
3. export_metadata()        – Export API (published versions only)
4. bulk_metadata_to_csv()   – harvest all published datasets to CSV

Usage
-----
  # Download full metadata for the specific DRAFT dataset (requires token)
  python dataverse_metadata_radogost.py \
      --mode draft \
      --api-token YOUR_TOKEN \
      --output GKBKTC_draft.json

  # Bulk CSV of all published datasets (no token needed for public records)
  python dataverse_metadata_radogost.py \
      --mode bulk \
      --output radogost_datasets.csv

  # Export a single published dataset as Datacite XML
  python dataverse_metadata_radogost.py \
      --mode export \
      --pid doi:10.82343/GKBKTC \
      --format Datacite \
      --output GKBKTC.xml \
      --api-token YOUR_TOKEN

Dependencies
------------
  pip install requests tqdm
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

# ── Windows console: force UTF-8 so Unicode chars print correctly ─────────────
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass  # Python < 3.7: silently replace unencodable chars

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Instance defaults ────────────────────────────────────────────────────────
BASE_URL     = "https://radogost.dariah.pl"
TARGET_PID   = "doi:10.82343/GKBKTC"
TARGET_VER   = ":draft"          # use ":latest-published" for published version


# ============================================─────────────────
# HTTP client
# ============================================─────────────────

class DataverseClient:

    EXPORT_FORMATS = [
        "dataverse_json",
        "schema.org",
        "OAI_ORE",
        "Datacite",
        "oai_datacite",
        "oai_dc",
        "dcterms",
    ]

    def __init__(
        self,
        base_url: str = BASE_URL,
        api_token: Optional[str] = None,
        timeout: int = 30,
        retry_delay: float = 2.0,
        max_retries: int = 3,
    ) -> None:
        self.base_url    = base_url.rstrip("/")
        self.timeout     = timeout
        self.retry_delay = retry_delay
        self.max_retries = max_retries
        self.session     = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        if api_token:
            self.session.headers.update({"X-Dataverse-key": api_token})

    # ------------------------------------------------------------------
    def get(self, endpoint: str, params: dict | None = None) -> dict:
        url = f"{self.base_url}{endpoint}"
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
            except requests.HTTPError as exc:
                code = exc.response.status_code
                log.warning("HTTP %s on %s (attempt %d/%d)", code, url, attempt, self.max_retries)
                if code == 401:
                    raise PermissionError(
                        "HTTP 401 – Authorisation failed. "
                        "Supply a valid --api-token (required for DRAFT datasets)."
                    ) from exc
                if code == 404:
                    raise FileNotFoundError(
                        f"HTTP 404 – Dataset not found at {url}. "
                        "Check the PID and version string."
                    ) from exc
                if code in {429, 503}:
                    time.sleep(self.retry_delay * attempt)
                else:
                    raise
            except requests.RequestException as exc:
                log.warning("Request error: %s (attempt %d/%d)", exc, attempt, self.max_retries)
                time.sleep(self.retry_delay * attempt)
        raise RuntimeError(f"Failed to GET {url} after {self.max_retries} retries")

    def get_raw(self, endpoint: str, params: dict | None = None) -> bytes:
        url = f"{self.base_url}{endpoint}"
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.content


# ============================================─────────────────
# 1. Single dataset – full native JSON (supports DRAFT)
# ============================================─────────────────

def fetch_full_metadata(
    client: DataverseClient,
    pid: str = TARGET_PID,
    version: str = TARGET_VER,
) -> dict[str, Any]:
    """
    Retrieve the complete native-JSON metadata for any dataset version,
    including DRAFT.  DRAFT access requires an API token with edit rights.

    Endpoint: GET /api/datasets/:persistentId/versions/{version}
              ?persistentId={pid}

    Special version strings:
        :draft              – current draft (token required)
        :latest             – most recent version (draft if it exists)
        :latest-published   – most recent published version
        1.0, 2.1, …        – specific numeric version
    """
    log.info("Fetching metadata for %s @ version %s …", pid, version)
    data = client.get(
        f"/api/datasets/:persistentId/versions/{version}",
        params={"persistentId": pid},
    )
    return data["data"]


def flatten_citation(meta: dict[str, Any]) -> dict[str, Any]:
    """
    Flatten the citation metadata block into a simple key→value dict
    for easy CSV / pandas ingestion.
    """
    blocks   = meta.get("metadataBlocks", {})
    citation = blocks.get("citation", {}).get("fields", [])

    flat: dict[str, Any] = {
        "persistentId":   meta.get("datasetPersistentId", ""),
        "versionNumber":  meta.get("versionNumber"),
        "versionState":   meta.get("versionState"),
        "createTime":     meta.get("createTime"),
        "lastUpdateTime": meta.get("lastUpdateTime"),
        "license":        meta.get("license", {}).get("name", "") if isinstance(meta.get("license"), dict) else meta.get("license", ""),
    }

    for field in citation:
        name     = field["typeName"]
        value    = field.get("value")
        multiple = field.get("multiple", False)

        if name == "author" and isinstance(value, list):
            flat["authors"] = "; ".join(
                a.get("authorName", {}).get("value", "") for a in value
            )
            flat["authorAffiliations"] = "; ".join(
                a.get("authorAffiliation", {}).get("value", "") for a in value
                if a.get("authorAffiliation")
            )
        elif name == "datasetContact" and isinstance(value, list):
            flat["contactEmails"] = "; ".join(
                c.get("datasetContactEmail", {}).get("value", "") for c in value
            )
            flat["contactNames"] = "; ".join(
                c.get("datasetContactName", {}).get("value", "") for c in value
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
        elif name == "publication" and isinstance(value, list):
            flat["relatedPublications"] = "; ".join(
                p.get("publicationCitation", {}).get("value", "") for p in value
                if p.get("publicationCitation")
            )
        elif name == "contributor" and isinstance(value, list):
            flat["contributors"] = "; ".join(
                c.get("contributorName", {}).get("value", "") for c in value
                if c.get("contributorName")
            )
        elif name == "producer" and isinstance(value, list):
            flat["producers"] = "; ".join(
                p.get("producerName", {}).get("value", "") for p in value
                if p.get("producerName")
            )
        elif multiple and isinstance(value, list):
            flat[name] = "; ".join(str(v) for v in value)
        else:
            flat[name] = value

    return flat


def summarise_files(meta: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Return a list of file-level metadata dicts from the dataset version.
    Useful for auditing what data files are attached to the dataset.
    """
    files = []
    for f in meta.get("files", []):
        dm = f.get("dataFile", {})
        files.append({
            "fileId":        dm.get("id"),
            "filename":      dm.get("filename"),
            "contentType":   dm.get("contentType"),
            "filesize":      dm.get("filesize"),
            "md5":           dm.get("md5"),
            "description":   f.get("description", ""),
            "directoryLabel":f.get("directoryLabel", ""),
            "restricted":    f.get("restricted", False),
        })
    return files


# ============================================─────────────────
# 2. Search API – paginated list (published datasets only)
# ============================================─────────────────

def search_datasets(
    client: DataverseClient,
    query: str = "*",
    subtree: Optional[str] = None,
    per_page: int = 1000,
    metadata_fields: Optional[list[str]] = None,
) -> Generator[dict[str, Any], None, None]:
    """
    Yield one dict per *published* dataset via the Dataverse Search API.
    Draft datasets are not reachable through the Search API.
    """
    params: dict[str, Any] = {
        "q":        query,
        "type":     "dataset",
        "per_page": per_page,
        "start":    0,
        "sort":     "date",
        "order":    "asc",
    }
    if subtree:
        params["subtree"] = subtree
    if metadata_fields:
        params["metadata_fields"] = metadata_fields

    total: Optional[int] = None
    fetched = 0

    with tqdm(desc="Searching published datasets", unit=" ds", total=None) as bar:
        while True:
            data  = client.get("/api/search", params=params)
            items = data["data"]["items"]

            if total is None:
                total    = data["data"]["total_count"]
                bar.total = total
                log.info("Total published datasets on %s: %d", client.base_url, total)

            for item in items:
                yield item
                fetched += 1
                bar.update(1)

            params["start"] += per_page
            if params["start"] >= (total or 0):
                break
            time.sleep(0.1)

    log.info("Search complete: %d datasets retrieved", fetched)


# ============================================─────────────────
# 3. Export API (published versions, standard formats)
# ============================================─────────────────

def export_metadata(
    client: DataverseClient,
    pid: str = TARGET_PID,
    export_format: str = "dataverse_json",
) -> bytes:
    """
    Export the latest *published* version of a dataset.
    Note: the Export API does NOT serve DRAFT versions.
    For drafts use fetch_full_metadata() instead.
    """
    log.info("Exporting %s as %s …", pid, export_format)
    return client.get_raw(
        "/api/datasets/export",
        params={"exporter": export_format, "persistentId": pid},
    )


# ============================================─────────────────
# 4. Bulk harvest → CSV (published datasets)
# ============================================─────────────────

SEARCH_COLUMNS = [
    "name", "global_id", "description", "url", "published_at",
    "publisher", "subjects", "fileCount", "versionId", "versionState",
    "citation",
]

def bulk_metadata_to_csv(
    client: DataverseClient,
    output_path: Path,
    query: str = "*",
    subtree: Optional[str] = None,
    fetch_full: bool = False,
) -> int:
    """
    Write a CSV of all published datasets on the Dataverse instance.
    With fetch_full=True, an extra Native API call per dataset enriches the
    output with the full citation block (authors, keywords, description, etc.).
    """
    first_row = True
    writer    = None
    count     = 0

    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        for item in search_datasets(
            client,
            query=query,
            subtree=subtree,
            metadata_fields=["citation:*", "geospatial:*"],
        ):
            row: dict[str, Any] = {col: item.get(col, "") for col in SEARCH_COLUMNS}

            if fetch_full:
                pid = item.get("global_id")
                if pid:
                    try:
                        full  = fetch_full_metadata(client, pid, version=":latest-published")
                        extra = flatten_citation(full)
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

    log.info("Wrote %d datasets to %s", count, output_path)
    return count


# ============================================─────────────────
# CLI
# ============================================─────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Download metadata from radogost.dariah.pl (DARIAH-PL Dataverse).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--base-url",   default=BASE_URL,    help="Dataverse base URL.")
    p.add_argument("--api-token",  default=None,        help="API token (required for DRAFT access).")
    p.add_argument("--output",     default="output.json", help="Output file path.")
    p.add_argument(
        "--mode",
        choices=["draft", "export", "bulk"],
        default="draft",
        help=(
            "draft  – fetch full metadata for the target DRAFT dataset (default);\n"
            "export – export published version in a standard format;\n"
            "bulk   – harvest all published datasets to CSV."
        ),
    )
    p.add_argument("--pid",     default=TARGET_PID, help="Dataset PID (overrides default).")
    p.add_argument("--version", default=TARGET_VER, help="Version string (default: :draft).")
    p.add_argument(
        "--format",
        default="dataverse_json",
        choices=DataverseClient.EXPORT_FORMATS,
        help="Export format for --mode export.",
    )
    p.add_argument("--fetch-full", action="store_true", help="(bulk mode) Enrich with Native API metadata.")
    p.add_argument("--subtree",    default=None,         help="(bulk mode) Restrict to a collection alias.")
    return p


def main(argv: list[str] | None = None) -> None:
    args   = build_parser().parse_args(argv)
    client = DataverseClient(base_url=args.base_url, api_token=args.api_token)

    # ── DRAFT mode ============================================
    if args.mode == "draft":
        meta  = fetch_full_metadata(client, pid=args.pid, version=args.version)
        flat  = flatten_citation(meta)
        files = summarise_files(meta)

        output = Path(args.output)
        payload = {
            "citation_flat": flat,
            "files":         files,
            "raw_metadata":  meta,
        }
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        log.info("Saved draft metadata to %s", output)

        # Human-readable summary
        print("\n== Dataset summary ==")
        print(f"  Title      : {flat.get('title', 'N/A')}")
        print(f"  PID        : {flat.get('persistentId', args.pid)}")
        print(f"  Version    : {flat.get('versionState', '')} {flat.get('versionNumber', '')}")
        print(f"  Authors    : {flat.get('authors', 'N/A')}")
        print(f"  Subjects   : {flat.get('subjects', 'N/A')}")
        print(f"  Keywords   : {flat.get('keywords', 'N/A')}")
        print(f"  Files      : {len(files)}")
        print(f"  Saved to   : {output}")
        print("=" * 44 + "\n")

    # ── EXPORT mode ───────────────────────────────────────────────────────────
    elif args.mode == "export":
        raw    = export_metadata(client, pid=args.pid, export_format=args.format)
        output = Path(args.output)
        output.write_bytes(raw)
        log.info("Saved %s export to %s (%d bytes)", args.format, output, len(raw))

    # ── BULK CSV mode ─────────────────────────────────────────────────────────
    elif args.mode == "bulk":
        n = bulk_metadata_to_csv(
            client,
            output_path=Path(args.output),
            subtree=args.subtree,
            fetch_full=args.fetch_full,
        )
        print(f"\nDone -- {n} datasets written to {args.output}")


if __name__ == "__main__":
    main()
