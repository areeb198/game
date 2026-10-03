"""Fail the release job when an artifact is not actually signed.

buildozer only appends --sign to the python-for-android command when the four
P4A_RELEASE_* environment variables exist, and it reports the miss as a plain
error line while still exiting 0. An unsigned build therefore succeeds and gets
uploaded, so the artifacts are checked structurally instead of by file name,
and the App Bundle is additionally put through jarsigner.

usage: verify_signed_artifacts.py <directory>
"""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

# final 16 bytes of the APK Signing Block (schemes v2 / v3), which sits
# immediately before the zip central directory
APK_SIG_BLOCK_MAGIC = b"APK Sig Block 42"


def signature_entries(names):
    found = []
    for name in names:
        upper = name.upper()
        if not upper.startswith("META-INF/"):
            continue
        if upper.endswith((".RSA", ".DSA", ".EC", ".SF")):
            found.append(name)
    return sorted(found)


def is_v1_signed(entries):
    has_digest = any(n.upper().endswith(".SF") for n in entries)
    has_block = any(n.upper().endswith((".RSA", ".DSA", ".EC")) for n in entries)
    return has_digest and has_block


def jarsigner_rejects(path):
    """Return why jarsigner refuses the bundle, or None once it verifies.

    The exit status is useless as a guard: jarsigner reports an unsigned jar
    with status 0 and a correctly signed, self-signed one with status 4, so
    only the report text separates the two.
    """
    jarsigner = shutil.which("jarsigner")
    if jarsigner is None:
        return "jarsigner is not on PATH (actions/setup-java provides it)"

    run = subprocess.run(
        [jarsigner, "-verify", str(path)],
        capture_output=True,
        text=True,
        errors="replace",
    )
    report = (run.stdout or "") + (run.stderr or "")
    if "jar verified" in report:
        return None
    for line in report.splitlines():
        if line.strip():
            return line.strip()
    return "jarsigner produced no report"


def main(argv):
    if len(argv) != 2:
        print("usage: verify_signed_artifacts.py <directory>", file=sys.stderr)
        return 2

    directory = Path(argv[1])
    if not directory.is_dir():
        print(f"::error::{directory} is not a directory")
        return 1

    artifacts = sorted(
        p for p in directory.iterdir() if p.suffix.lower() in (".apk", ".aab")
    )
    if not artifacts:
        print(f"::error::no .apk or .aab produced in {directory}")
        return 1

    failures = []
    for path in artifacts:
        with zipfile.ZipFile(path) as archive:
            entries = signature_entries(archive.namelist())

        if path.suffix.lower() == ".apk":
            v1 = is_v1_signed(entries)
            v2 = APK_SIG_BLOCK_MAGIC in path.read_bytes()
            if not (v1 or v2):
                failures.append(
                    f"{path.name} carries no v1 and no v2/v3 signature - the "
                    "P4A_RELEASE_* variables did not reach buildozer"
                )
                continue
            schemes = " + ".join(s for s, ok in (("v1", v1), ("v2/v3", v2)) if ok)
            print(f"{path.name}: signed ({schemes})")
        else:
            if not is_v1_signed(entries):
                failures.append(
                    f"{path.name} has no META-INF signature - the "
                    "P4A_RELEASE_* variables did not reach python-for-android"
                )
                continue
            reject = jarsigner_rejects(path)
            if reject:
                failures.append(f"{path.name} failed jarsigner verification: {reject}")
                continue
            print(f"{path.name}: signed (v1, jarsigner verified)")

    for failure in failures:
        print(f"::error::{failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
