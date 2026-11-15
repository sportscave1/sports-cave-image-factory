"""Build a reviewed local Windows archive; never installs, publishes or deploys it."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from task_recorder.release import build_package, digest, verify_archive


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--native", type=Path, default=ROOT / "windows-screen-recorder/native/bin/DesktopRecorder.exe")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    data = build_package(ROOT, args.native)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    print("Package: " + str(args.output.resolve()))
    print("SHA-256: " + digest(data))
    print("Manifest: " + verify_archive(data))


if __name__ == "__main__":
    main()
