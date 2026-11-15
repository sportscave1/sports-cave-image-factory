"""Output structure captured from clean main, independent of upgraded visual prose."""
import re


def contract_shape(prompt):
    return {
        "output_headings": re.findall(
            r"^(?:GROUP [1-5] [^\n]+|(?:IMAGE GENERATION PROMPT|AD COPY|CSV OUTPUT|OUTPUT FORMAT|PRIMARY TEXTS?|HEADLINES?|DESCRIPTIONS?)(?: [1-5])?[: ]*)$",
            prompt, re.M),
        "csv_headers": sorted(set(re.findall(
            r"^\s*(?:[a-z][a-z_]*,){3,}[a-z][a-z_]*\s*$", prompt, re.M))),
        "template_variables": sorted(set(re.findall(r"\{\{?[A-Z][A-Z_ ]+\}?\}", prompt))),
        "output_dimensions": sorted(set(re.findall(r"\b\d{3,4}\s*[x×]\s*\d{3,4}\b", prompt))),
        "product_urls": sorted(set(re.findall(r"https?://[^\s\"<>]+/products/[^\s\"<>]+", prompt))),
        "schema_keys": sorted(set(re.findall(r'"([a-z][a-z_0-9]*)"\s*:', prompt))
                              - {"camera_angle_refinement"}),
    }
