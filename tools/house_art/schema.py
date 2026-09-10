"""The `description.json` contract, and its validator.

A description is the *only* input the drawing code has. It is also the record of
which reference pages a person looked at while writing it. Both halves matter:

  - the element names are what `checks.check_description` holds the drawing to,
    so a part cannot appear in the artwork without being described first;
  - `references` are URLs, never files. Reference images are fetched to a
    gitignored working directory so a human can look at them, and are never
    stored in the repository (ASSET-LICENSING: we host only what we are licensed
    to host, and we are not licensed to host these).

Evidence grade is a required, human judgement about how well-founded the
drawing is:

  A  agency render plus photographs
  B  one clear image of the spacecraft
  C  thin: a single diagram, or only imagery of a sibling vehicle

Grade C is legitimate — for several derivative-refused owners it is all that
exists — but it is shown on the review page so the reviewer can spend attention
where the evidence is weakest.
"""

EVIDENCE_GRADES = ("A", "B", "C")

# Required top-level keys. `bus` and `distinctive` are required because a
# description with neither is not a description of a spacecraft.
REQUIRED = ("folder", "mission", "evidence", "evidence_note", "bus",
            "solar", "distinctive", "references")

# Optional keys the rest of the lane understands.
OPTIONAL = ("agency", "owner", "mission_id", "instruments", "antennas", "booms",
            "deliberately_omitted", "shares_bus_with", "reference_caveat",
            "generation_route", "icon_derivation", "svg", "pilot")


class DescriptionError(ValueError):
    """A description that the drawing code must not be run against."""


def element_names(d):
    """The element names this description promises the drawing will contain.

    This is the contract `checks.check_description` enforces. Keep it in step
    with the drawing vocabulary: a `with scene.part(name)` block must use one of
    these names exactly.
    """
    names = set()
    if d.get("bus"):
        names.add("bus")
    solar = d.get("solar") or {}
    if solar.get("wings"):
        names.add("solar array")
    for key in ("instruments", "antennas", "booms"):
        for item in d.get(key) or []:
            if item.get("name"):
                names.add(item["name"])
    return names


def omitted_names(d):
    """Elements deliberately left out, with a stated reason.

    This exists because of a real failure: a drawing once carried a star tracker
    that appeared in no reference and in no description. The fix is not to
    describe it after the fact but to remove it — and, when a reviewer asks
    "where is the X", to be able to say in the file why it is not there.
    """
    return {x["element"] for x in (d.get("deliberately_omitted") or [])
            if isinstance(x, dict) and x.get("element")}


def _is_url(value):
    return isinstance(value, str) and value.startswith(("https://", "http://"))


def validate(d, folder=None):
    """Return a list of problems; empty means valid. Never raises on content."""
    problems = []
    if not isinstance(d, dict):
        return ["description is not an object"]

    for key in REQUIRED:
        if key not in d or d[key] in ("", None, [], {}):
            problems.append(f"missing required key: {key}")

    if folder is not None and d.get("folder") != folder:
        problems.append(f"folder {d.get('folder')!r} does not match "
                        f"the directory it was loaded from ({folder!r})")

    grade = d.get("evidence")
    if grade not in EVIDENCE_GRADES:
        problems.append(f"evidence must be one of {EVIDENCE_GRADES}, found {grade!r}")

    refs = d.get("references")
    if not isinstance(refs, list) or not refs:
        problems.append("references must be a non-empty list")
    else:
        for i, r in enumerate(refs):
            if not isinstance(r, dict):
                problems.append(f"references[{i}] is not an object")
                continue
            if not _is_url(r.get("source_page")):
                problems.append(f"references[{i}].source_page must be a URL, "
                                f"found {r.get('source_page')!r}")
            # A reference must never carry a path into the repository: the whole
            # point is that we record where we looked, not what we kept.
            for key in ("file", "path", "local_path"):
                if r.get(key):
                    problems.append(f"references[{i}].{key} is set — reference "
                                    f"images are never stored in the repository, "
                                    f"only their URLs")
        if not any(r.get("used_for_geometry") for r in refs if isinstance(r, dict)):
            problems.append("no reference is marked used_for_geometry — at least "
                            "one reference must have informed the drawing")

    for key in ("instruments", "antennas", "booms"):
        items = d.get(key)
        if items is None:
            continue
        if not isinstance(items, list):
            problems.append(f"{key} must be a list")
            continue
        for i, item in enumerate(items):
            if not isinstance(item, dict) or not item.get("name"):
                problems.append(f"{key}[{i}] needs a name")
            elif not item.get("form"):
                problems.append(f"{key}[{i}] ({item['name']}) needs a form: "
                                f"what shape is it, so it can be drawn")

    for i, x in enumerate(d.get("deliberately_omitted") or []):
        if not isinstance(x, dict) or not x.get("element") or not x.get("reason"):
            problems.append(f"deliberately_omitted[{i}] needs element and reason "
                            f"— an omission without a stated reason is just a gap")

    unknown = set(d) - set(REQUIRED) - set(OPTIONAL)
    if unknown:
        problems.append(f"unknown keys: {sorted(unknown)}")

    return problems


def validate_or_raise(d, folder=None):
    problems = validate(d, folder)
    if problems:
        raise DescriptionError("; ".join(problems))
    return d


def reference_urls(d):
    """The URL list that goes into index.json for this folder."""
    return [r["source_page"] for r in d.get("references") or []
            if isinstance(r, dict) and _is_url(r.get("source_page"))]
