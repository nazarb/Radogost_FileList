"""
generate_readme.py
==================
Generate a README.md from a locally saved Dataverse metadata JSON file,
following the style of the UnderTheSands / RADOGOST README convention:

  - Principal Investigator + Co-Investigator blocks (first author = PI)
  - Structured funding paragraph
  - File list with naming-schema section
  - Data-specific information tables (one per file type)
  - Materials & instruments block
  - ARIADNEplus block

No API calls – works entirely offline.

Usage
-----
  python generate_readme.py                              # uses GKBKTC_draft.json
  python generate_readme.py --input other.json --output README.md

Dependencies
------------
  pip install jinja2
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

from jinja2 import Environment, BaseLoader

# ── Windows console: force UTF-8 so Polish/Unicode chars print correctly ──────
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass  # Python < 3.7 fallback

README_TEMPLATE = """\
This readme file was generated on {{ currentDate }} by {{ creatorName }}


# GENERAL INFORMATION

* Title of Dataset:
  {{ title }}
{% if titleTranslation %}
* Title translation ({{ titleTranslation.language }}):
  {{ titleTranslation.text }}
{% endif %}

## Principal Investigator Information
Name: {{ pi.authorName }}
{% if pi.authorIdentifierScheme %}{{ pi.authorIdentifierScheme }}: {{ pi.authorIdentifier }}{% if pi.authorAffiliationIdentifier %}  –  ROR: {{ pi.authorAffiliationIdentifier }}{% endif %}
{% endif %}
Institution: {{ pi.authorAffiliation }}
Address: [Address]
Email: [Email]
{% for co in coAuthors %}

## Co-investigator Information
Name: {{ co.authorName }}
{% if co.authorIdentifierScheme %}{{ co.authorIdentifierScheme }}: {{ co.authorIdentifier }}{% endif %}

Institution: {{ co.authorAffiliation }}
Address: [Address]
Email: [Email]
{% endfor %}
{% if dateOfCollection %}
## Date of data collection:
{% for d in dateOfCollection %}from {{ d.dateOfCollectionStart | default('[YYYY-MM-DD]') }}{% if d.dateOfCollectionEnd %} to {{ d.dateOfCollectionEnd }}{% endif %}

{% endfor %}{% else %}
## Date of data collection:
[YYYY-MM-DD]
{% endif %}

## Geographic location of data collection:
{% if geographicBoundingBox %}
{{ geographicBoundingBox.coordinates }}

Site name: {{ geographicBoundingBox.name }}
Altitude:  {{ geographicBoundingBox.altMin }}{% if geographicBoundingBox.altMax and geographicBoundingBox.altMax != geographicBoundingBox.altMin %} – {{ geographicBoundingBox.altMax }}{% endif %} m a.s.l.
GeoNames ID: {{ geographicBoundingBox.geoname }}
{% else %}
[Coordinates or city/region, province/state, and country]
{% endif %}

## Funding Information
{% if grantNumber %}{% for g in grantNumber %}
This research was funded by {{ g.grantNumberAgency }}{% if g.grantNumberValue %} (grant no. {{ g.grantNumberValue }}){% endif %}.
{% endfor %}{% else %}
[Information about funding sources.]
{% endif %}


# SHARING/ACCESS INFORMATION

## Licenses/restrictions placed on the data:

{{ license if license else '[License information]' }}

## Recommended citation for this dataset:

{{ dsCitation if dsCitation else '[The preferred citation that others should use when citing the dataset.]' }}


# DATA & FILE OVERVIEW

## File List:
{% for f in dataFile %}
{{ f.filename }}{% if f.description %} - {{ f.description }}{% endif %}

{% endfor %}

## File naming conventions:
[The file naming conventions used to name your files.]


# METHODOLOGICAL INFORMATION

## Description of methods used for collection/generation of data:
[A brief description of methods used for collecting or generating data.]


## Methods for processing the data:
[Information about any software or instruments used to process the data.]


## Instrument- or software-specific information needed to interpret the data:
[Describe any specialist software needed to open or use the files.]


# DATA-SPECIFIC INFORMATION
{% for f in dataFile %}
## DATA-SPECIFIC INFORMATION FOR: {{ f.filename }}

* File format : {{ f.contentType }}
* File size   : {{ f.filesize_mb }} MB
* MD5 checksum: {{ f.md5 }}
* Access      : {% if f.restricted %}Restricted{% else %}Open{% endif %}

* Number of variables: [N]
* Number of cases/rows: [N]
* Variable List:
  [variable] – [description]

{% endfor %}

# ARCHAEOLOGICAL METADATA (ARIADNEplus)
{% if periodo %}
## Chronological periods (PeriodO URIs):
{% for p in periodo %}  - {{ p }}
{% endfor %}
{% endif %}
## Heritage type  : {{ archaeologicalHeritage | join('; ') if archaeologicalHeritage else '[N/A]' }}
## Research type  : {{ archaeologicalResearchType | join('; ') if archaeologicalResearchType else '[N/A]' }}
{% if rightsOwner %}
## Rights owner:
{% for ro in rightsOwner %}  - {{ ro.name }}{% if ro.url %}  ({{ ro.url }}){% endif %}

{% endfor %}{% endif %}
{% if scholarlyResponsibleEntity %}
## Scholarly responsible entity:
{% for sre in scholarlyResponsibleEntity %}  - {{ sre.name }}{% if sre.orcid %} (ORCID: {{ sre.orcid }}){% endif %}, {{ sre.affiliation }}
{% endfor %}{% endif %}


# ADDITIONAL INFORMATION

## Keywords:
{{ keywordValue | join('; ') if keywordValue else '[keywords]' }}


## Subject areas:
{{ subjects | join('; ') if subjects else '[subjects]' }}

Discipline (MEiN 2022): {{ disciplineMEiN2022 | join('; ') if disciplineMEiN2022 else '[N/A]' }}
Field of R&D: {{ fieldOfResearchAndDevelopment | join('; ') if fieldOfResearchAndDevelopment else '[N/A]' }}


## Language:
Data          : {{ languageOfData | join('; ') if languageOfData else '[N/A]' }}
Documentation : {{ languageOfDocumentation | join('; ') if languageOfDocumentation else '[N/A]' }}
Metadata      : {{ languageOfMetadata | join('; ') if languageOfMetadata else '[N/A]' }}


## Related publications:
{% if publication %}{% for p in publication %}
- {{ p.publicationCitation }}{% if p.publicationURL %}
  {{ p.publicationURL }}{% endif %}

  [Relation: {{ p.publicationRelationType }}]
{% endfor %}{% else %}
[Full citation 1]
{% endif %}

## Related datasets:
{% if relatedDatasets %}{% for rd in relatedDatasets %}
- {{ rd.citation }}
  DOI: {{ rd.doi }}
  Relation: {{ rd.relationType }}
{% endfor %}{% else %}
[Full citation 1]
{% endif %}

## References:
{% if publication %}{% for p in publication %}
{{ p.publicationCitation }}{% if p.publicationURL %} {{ p.publicationURL }}{% endif %}

{% endfor %}{% endif %}{% for rd in relatedDatasets %}
{{ rd.citation }} {{ rd.doi }}
{% endfor %}

## Notes:
{{ notesText if notesText else '[Additional notes]' }}
"""


def _field(fields: list[dict], type_name: str) -> Any:
    for f in fields:
        if f["typeName"] == type_name:
            return f.get("value")
    return None


def _sub(compound: dict, key: str) -> str:
    v = compound.get(key, {})
    return v.get("value", "") if isinstance(v, dict) else str(v or "")


def strip_html(text: str) -> str:
    text = re.sub(r"<p[^>]*>", "\n", text)
    text = re.sub(r"</p>", "", text)
    text = re.sub(r"·\s*", "  • ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def human_size(nb: int) -> str:
    return f"{nb / 1_048_576:.1f}"


def prim_list(citation: list[dict], tn: str) -> list[str]:
    v = _field(citation, tn)
    return v if isinstance(v, list) else ([v] if v else [])


def build_context(data: dict) -> dict[str, Any]:
    raw       = data["raw_metadata"]
    files_raw = data.get("files", [])
    blocks    = raw.get("metadataBlocks", {})
    citation  = blocks.get("citation",      {}).get("fields", [])
    geo       = blocks.get("geospatial",    {}).get("fields", [])
    ariadne   = blocks.get("archeoAriadne", {}).get("fields", [])

    # Title
    title = _field(citation, "title") or ""
    title_trans_raw = _field(citation, "titleTranslation")
    title_translation = None
    if title_trans_raw and isinstance(title_trans_raw, list):
        t = title_trans_raw[0]
        title_translation = {
            "text":     _sub(t, "titleTranslationText"),
            "language": _sub(t, "titleTranslationLanguage"),
        }

    # Authors → PI + Co-investigators
    raw_authors = _field(citation, "author") or []
    author_list = []
    for a in raw_authors:
        author_list.append({
            "authorName":                  _sub(a, "authorName"),
            "authorAffiliation":           _sub(a, "authorAffiliation"),
            "authorAffiliationIdentifier": _sub(a, "authorAffiliationIdentifier"),
            "authorIdentifierScheme":      _sub(a, "authorIdentifierScheme"),
            "authorIdentifier":            _sub(a, "authorIdentifier"),
        })
    pi         = author_list[0] if author_list else {}
    co_authors = author_list[1:]

    # Contacts
    contact_list = []
    for c in (_field(citation, "datasetContact") or []):
        contact_list.append({
            "datasetContactName":        _sub(c, "datasetContactName"),
            "datasetContactAffiliation": _sub(c, "datasetContactAffiliation"),
            "datasetContactEmail":       _sub(c, "datasetContactEmail"),
        })

    # Descriptions
    descriptions = [strip_html(_sub(d, "dsDescriptionValue"))
                    for d in (_field(citation, "dsDescription") or [])]

    # Keywords
    keywords = [_sub(k, "keywordValue") for k in (_field(citation, "keyword") or [])]

    # Publications
    pub_list = []
    for p in (_field(citation, "publication") or []):
        pub_list.append({
            "publicationCitation":     _sub(p, "publicationCitation"),
            "publicationURL":          _sub(p, "publicationURL"),
            "publicationRelationType": _sub(p, "publicationRelationType"),
        })

    # Related datasets
    related_ds = []
    for r in (_field(citation, "relatedDataset") or []):
        related_ds.append({
            "citation":     _sub(r, "relatedDatasetCitation"),
            "relationType": _sub(r, "relatedDatasetRelationType"),
            "doi":          _sub(r, "relatedDatasetIDNumber"),
        })

    # Date of collection
    date_coll = []
    for d in (_field(citation, "dateOfCollection") or []):
        date_coll.append({
            "dateOfCollectionStart": _sub(d, "dateOfCollectionStart"),
            "dateOfCollectionEnd":   _sub(d, "dateOfCollectionEnd"),
        })

    # Grants
    grants = []
    for g in (_field(citation, "grantNumber") or []):
        grants.append({
            "grantNumberAgency": _sub(g, "grantNumberAgency"),
            "grantNumberValue":  _sub(g, "grantNumberValue"),
        })

    # Geospatial bounding box
    bbox_raw = _field(geo, "geographicBoundingBox")
    geo_bbox = None
    if bbox_raw and isinstance(bbox_raw, dict):
        geo_bbox = {
            "name":        bbox_raw.get("geographicName",        {}).get("value", ""),
            "coordinates": bbox_raw.get("geographicCoordinates", {}).get("value", ""),
            "altMin":      bbox_raw.get("geographicAltitudeMin", {}).get("value", ""),
            "altMax":      bbox_raw.get("geographicAltitudeMax", {}).get("value", ""),
            "geoname":     "; ".join(_field(ariadne, "geoname") or []),
        }

    # ARIADNEplus
    periodo        = _field(ariadne, "periodo")                    or []
    arch_heritage  = _field(ariadne, "archaeologicalHeritage")     or []
    arch_research  = _field(ariadne, "archaeologicalResearchType") or []

    rights_owners = [{"name": _sub(ro, "roInstitutionName"),
                      "url":  _sub(ro, "roInstitutionWebsiteURL")}
                     for ro in (_field(ariadne, "rightsOwner") or [])]

    sre_list = [{"name":        _sub(sre, "srePersonName"),
                 "orcid":       _sub(sre, "srePersonIdentifier"),
                 "affiliation": _sub(sre, "srePersonAffiliation")}
                for sre in (_field(ariadne, "scholarlyResponsibleEntity") or [])]

    # License from first file entry in raw
    license_str = ""
    raw_files_full = raw.get("files", [])
    if raw_files_full:
        f0   = raw_files_full[0]
        name = f0.get("licenseName", "")
        url  = f0.get("licenseUrl",  "")
        license_str = f"{name}\n{url}" if url else name

    # Files
    file_list = []
    for f in files_raw:
        file_list.append({
            "filename":    f.get("filename", ""),
            "description": f.get("description", ""),
            "contentType": f.get("contentType", ""),
            "filesize_mb": human_size(f.get("filesize", 0)),
            "md5":         f.get("md5", ""),
            "restricted":  f.get("restricted", False),
        })

    # Version
    v_num   = raw.get("versionNumber")
    v_minor = raw.get("versionMinorNumber")
    ds_ver  = f"{v_num}.{v_minor}" if v_num is not None else raw.get("versionState", "DRAFT")

    return {
        "creatorName":               pi.get("authorName", ""),
        "currentDate":               date.today().isoformat(),
        "title":                     title,
        "titleTranslation":          title_translation,
        "pi":                        pi,
        "coAuthors":                 co_authors,
        "datasetContact":            contact_list,
        "dsDescriptionValue":        descriptions,
        "dateOfCollection":          date_coll,
        "geographicBoundingBox":     geo_bbox,
        "grantNumber":               grants,
        "keywordValue":              keywords,
        "subjects":                  prim_list(citation, "subject"),
        "disciplineMEiN2022":        prim_list(citation, "disciplineMEiN2022"),
        "fieldOfResearchAndDevelopment": prim_list(citation, "fieldOfResearchAndDevelopment"),
        "language":                  prim_list(citation, "language"),
        "languageOfData":            prim_list(citation, "languageOfData"),
        "languageOfDocumentation":   prim_list(citation, "languageOfDocumentation"),
        "languageOfMetadata":        prim_list(citation, "languageOfMetadata"),
        "license":                   license_str,
        "termsOfUse":                raw.get("termsOfUse", ""),
        "termsOfAccess":             raw.get("termsOfAccess", ""),
        "dsCitation":                "",
        "dataFile":                  file_list,
        "publication":               pub_list,
        "relatedDatasets":           related_ds,
        "notesText":                 _field(citation, "notesText") or "",
        "accessToSources":           _field(citation, "accessToSources") or "",
        "dsVersion":                 ds_ver,
        "periodo":                   periodo,
        "archaeologicalHeritage":    arch_heritage,
        "archaeologicalResearchType":arch_research,
        "rightsOwner":               rights_owners,
        "scholarlyResponsibleEntity":sre_list,
    }


def render(context: dict) -> str:
    env = Environment(
        loader=BaseLoader(),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env.from_string(README_TEMPLATE).render(**context)


def main():
    p = argparse.ArgumentParser(
        description="Generate README.md from a Dataverse draft JSON (UnderTheSands style)."
    )
    p.add_argument("--input",  default="GKBKTC_draft.json", help="Input JSON file.")
    p.add_argument("--output", default="README.md",         help="Output README file.")
    args = p.parse_args()

    data    = json.loads(Path(args.input).read_text(encoding="utf-8"))
    context = build_context(data)
    readme  = render(context)

    Path(args.output).write_text(readme, encoding="utf-8")
    print(f"OK README written to {args.output}")
    print(f"  Title   : {context['title']}")
    print(f"  PI      : {context['pi'].get('authorName','')}")
    print(f"  Co-inv. : {len(context['coAuthors'])}")
    print(f"  Files   : {len(context['dataFile'])}")
    print(f"  Version : {context['dsVersion']}")


if __name__ == "__main__":
    main()
