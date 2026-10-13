"""Local full-resolution pixel validation; no network or production operations."""
import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image


def print_readiness(size, paper_mm, specification_confirmed=False, bleed_confirmed=False, recommended_ppi=300):
    """Read-only print comparison. Unknown SKU/template requirements always block approval."""
    if len(size) != 2 or len(paper_mm) != 2 or any(v <= 0 or not math.isfinite(v) for v in (*size, *paper_mm)):
        raise ValueError("Invalid image or paper dimensions")
    pixels, mm = sorted(size), sorted(paper_mm)
    effective = [pixels[i] * 25.4 / mm[i] for i in range(2)]
    recommended = [math.ceil(v * recommended_ppi / 25.4) for v in mm]
    reasons = []
    if not specification_confirmed:
        reasons.append("Exact supplier SKU/size specifications not confirmed")
    if not bleed_confirmed:
        reasons.append("Exact bleed/template requirements not confirmed")
    if any(pixels[i] < recommended[i] for i in range(2)):
        reasons.append("Native pixels below supplier recommended resolution; no upscaling performed")
    return {"status": "BLOCKED" if reasons else "PASS", "paper_mm": list(paper_mm),
            "effective_ppi_short_long": effective, "recommended_pixels_short_long": recommended,
            "recommended_ppi": recommended_ppi, "reasons": reasons}


def region(before, after, size, padding=2, block=1):
    if len(before) != 4 or len(after) != 4 or not all(math.isfinite(v) for v in before + after):
        raise ValueError("Invalid verified text bounds")
    x0 = max(0, math.floor((min(before[0], after[0]) - padding) / block) * block)
    y0 = max(0, math.floor((min(before[1], after[1]) - padding) / block) * block)
    x1 = min(size[0], math.ceil((max(before[2], after[2]) + padding) / block) * block)
    y1 = min(size[1], math.ceil((max(before[3], after[3]) + padding) / block) * block)
    if x1 <= x0 or y1 <= y0 or (x1 - x0) * (y1 - y0) > size[0] * size[1] * .02:
        raise ValueError("Text verification region is empty or exceeds 2% of artwork")
    return [x0, y0, x1, y1]


def compare(before_path, after_path, roi):
    """Compare every pixel, in strips. Zero tolerance outside the verified ROI."""
    changed = outside = maximum = 0
    bbox = None
    with Image.open(before_path) as before, Image.open(after_path) as after:
        if before.size != after.size:
            raise ValueError("Export dimensions changed")
        width, height = before.size
        for top in range(0, height, 128):
            bottom = min(height, top + 128)
            a = np.asarray(before.crop((0, top, width, bottom)).convert("RGBA"), dtype=np.int16)
            b = np.asarray(after.crop((0, top, width, bottom)).convert("RGBA"), dtype=np.int16)
            delta = np.abs(a - b)
            maximum = max(maximum, int(delta.max()))
            mask = np.any(delta != 0, axis=2)
            count = int(mask.sum())
            changed += count
            if count:
                yy, xx = np.nonzero(mask)
                local = [int(xx.min()), int(yy.min() + top), int(xx.max() + 1), int(yy.max() + top + 1)]
                bbox = local if bbox is None else [min(bbox[0], local[0]), min(bbox[1], local[1]), max(bbox[2], local[2]), max(bbox[3], local[3])]
            mask[max(0, roi[1] - top):max(0, min(bottom, roi[3]) - top), roi[0]:roi[2]] = False
            outside += int(mask.sum())
    return {"ok": changed > 0 and outside == 0, "changed_pixels": changed,
            "outside_region_pixels": outside, "changed_bbox": bbox, "max_channel_delta": maximum,
            "allowed_region": roi, "tolerance": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    data = json.loads(args.report.read_text(encoding="utf-8-sig"))
    for record in data["documents"]:
        if not record.get("structural_verification"):
            continue
        size = (record["width"], record["height"])
        roi = region(record["number_bounds_before"], record["number_bounds_after"], size)
        record["lossless_pixels"] = compare(record["before_png"], record["after_png"], roi)
        # JPEG transform/subsampling can affect neighbouring 8/16px blocks: separate bounded check.
        jpeg_roi = region(record["number_bounds_before"], record["number_bounds_after"], size, padding=32, block=16)
        record["jpeg_pixels"] = compare(record["before_jpg"], record["after_jpg"], jpeg_roi)
        with Image.open(record["after_jpg"]) as jpg:
            record["jpg_reopened"] = {"size": list(jpg.size), "dpi": [float(v) for v in jpg.info.get("dpi", [])], "icc_profile_present": bool(jpg.info.get("icc_profile"))}
            if jpg.size != size:
                raise ValueError("JPG resolution changed")
            if len(record["jpg_reopened"]["dpi"]) != 2 or any(abs(v - record["resolution"]) > .001 for v in record["jpg_reopened"]["dpi"]):
                raise ValueError("JPG print resolution metadata changed")
            if not record["jpg_reopened"]["icc_profile_present"]:
                raise ValueError("JPG colour profile is missing")
        crop_roi = jpeg_roi
        before = Image.open(record["before_png"]).crop(crop_roi).convert("RGB")
        after = Image.open(record["after_png"]).crop(crop_roi).convert("RGB")
        comparison = Image.new("RGB", (before.width * 2, before.height))
        comparison.paste(before, (0, 0)); comparison.paste(after, (before.width, 0))
        record["badge_comparison"] = str(Path(record["psd"]).with_suffix(".badge-before-after.png"))
        comparison.save(record["badge_comparison"])
        record["status"] = "Verified local proof" if record["lossless_pixels"]["ok"] and record["jpeg_pixels"]["ok"] else "Blocked: visual difference outside verified number region"
    target = args.report.with_name("verified-export-proof.json")
    target.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps([{k: r.get(k) for k in ("product_title", "status", "error", "width", "height", "lossless_pixels", "jpeg_pixels")} for r in data["documents"]]))


if __name__ == "__main__":
    main()
