import json
import csv
import re
from pathlib import Path

# ── configuration ─────────────────────────────────────────────────────────────
JSON_PATH  = Path("PSEYXF_draft.json")          # input file
CSV_PATH   = Path("PSEYXF_files.csv")           # output file
BASE_URL   = "https://radogost.dariah.pl"        # Dataverse instance base URL
# ──────────────────────────────────────────────────────────────────────────────

COLUMNS = [
    "fileId",
    "filename",
    "contentType",
    "filesize_bytes",
    "filesize_mb",
    "restricted",
    "md5",
    "inscription",        # text extracted from „…" in Opis na przeźroczu
    "description",
    "download_url",
]

# Matches the quoted text after "Opis na przeźroczu:" using Polish/German
# opening „ (\u201e) or " (\u201c) and closing " (\u201d) or " (\u201c)
_INSCRIPTION_RE = re.compile(
    r'Opis na przeźroczu\s*:\s*[\u201e\u201c\u201d"]([^\u201d\u201c"]+)[\u201d\u201c"]',
    re.DOTALL,
)


def extract_inscription(description: str) -> str:
    """Return the slide inscription text found between „…" / "…"."""
    m = _INSCRIPTION_RE.search(description)
    return m.group(1).strip() if m else ""


def build_download_url(file_id: int, base_url: str) -> str:
    """Radogost file viewer URL."""
    return f"{base_url.rstrip('/')}/file.xhtml?fileId={file_id}"


def human_size(n_bytes: int) -> str:
    if n_bytes < 1_024:
        return f"{n_bytes} B"
    if n_bytes < 1_048_576:
        return f"{n_bytes / 1024:.1f} KB"
    return f"{n_bytes / 1_048_576:.2f} MB"


def main() -> None:
    with JSON_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)

    files = data["files"]
    print(f"Found {len(files)} file records.")

    # --- quick preview of what the regex pulls out ---
    print("\nInscription extraction preview:")
    matched = 0
    for f in files:
        ins = extract_inscription(f.get("description", ""))
        status = "✓" if ins else "–"
        print(f"  {status}  [{f['fileId']}] {f['filename'][:45]:<45}  {ins[:60]}")
        if ins:
            matched += 1

    print(f"\nMatched {matched}/{len(files)} files.\n")

    with CSV_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()

        for f in files:
            desc = f.get("description", "").strip()
            writer.writerow({
                "fileId":         f["fileId"],
                "filename":       f["filename"],
                "contentType":    f["contentType"],
                "filesize_bytes": f["filesize"],
                "filesize_mb":    human_size(f["filesize"]),
                "restricted":     f.get("restricted", False),
                "md5":            f.get("md5", ""),
                "inscription":    extract_inscription(desc),
                "description":    desc,
                "download_url":   build_download_url(f["fileId"], BASE_URL),
            })

    print(f"CSV written → {CSV_PATH}  ({CSV_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
