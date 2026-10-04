"""Prove the built APK will pass Google Play's upload-time checks.

``buildozer.spec`` saying ``android.api = 36`` only means we asked for it.
Gradle is what actually stamps ``targetSdkVersion`` into the manifest, and
Play Console reads the manifest: since 31 Aug 2026 an upload below API 36 is
rejected at submission. So we dump the real badging from the artifact.

Also cross-checks the application id and versionCode against the spec, because
both are effectively permanent once Play accepts a package:

* the id can never be changed,
* the versionCode must strictly increase on every upload, so silently falling
  back to p4a's automatic computation would eventually ship a value you cannot
  reuse.
"""

import pathlib
import re
import shutil
import subprocess
import sys

# developer.android.com/google/play/requirements/target-sdk
PLAY_MIN_API = 36


def fail_collect(messages, message):
    messages.append(message)


def read_spec_keys(path):
    keys = {}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return keys, f"cannot read {path}: {exc}"
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped[0] in "#;":
            continue
        key, sep, value = stripped.partition("=")
        if sep:
            keys.setdefault(key.strip(), value.strip())
    return keys, None


def find_aapt():
    """Locate aapt inside buildozer's SDK, without walking the NDK."""
    roots = [
        pathlib.Path.home() / ".buildozer",
        pathlib.Path.cwd() / ".buildozer",
    ]
    for root in roots:
        for parent in (root / "android" / "platform",
                       root / "android" / "platform" / "android-sdk"):
            build_tools = parent / "build-tools"
            if not build_tools.is_dir():
                continue
            for version in sorted(build_tools.iterdir(), reverse=True):
                for name in ("aapt", "aapt.exe"):
                    cand = version / name
                    if cand.is_file():
                        return cand
    return shutil.which("aapt")


def dump_badging(aapt, apk):
    proc = subprocess.run([str(aapt), "dump", "badging", str(apk)],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip()
    return proc.stdout, None


def check_apk(aapt, apk, spec_keys, messages):
    text, err = dump_badging(aapt, apk)
    if text is None:
        fail_collect(messages, f"{apk.name}: aapt dump badging failed: {err}")
        return

    label = apk.name
    pkg = re.search(r"^package: name='([^']*)' versionCode='([^']*)' "
                    r"versionName='([^']*)'", text, re.M)
    target = re.search(r"^targetSdkVersion:'(\d+)'", text, re.M)
    minimum = re.search(r"^sdkVersion:'(\d+)'", text, re.M)
    icons = re.findall(r"^application-icon[^:]*:'([^']*)'", text, re.M)

    if not pkg:
        fail_collect(messages, f"{label}: could not parse the package line out "
                               "of aapt output")
        return

    name, version_code, version_name = pkg.groups()
    print(f"== {label}")
    print(f"   package      = {name}")
    print(f"   versionCode  = {version_code}  versionName = {version_name}")
    print(f"   minSdk       = {minimum.group(1) if minimum else '?'}")
    print(f"   targetSdk    = {target.group(1) if target else 'ABSENT'}")
    print(f"   icons        = {len(icons)}")

    if not target:
        fail_collect(messages, f"{label}: the manifest has no targetSdkVersion "
                               "at all, so Play treats it as API 1 and rejects "
                               "the upload.")
    else:
        value = int(target.group(1))
        if value < PLAY_MIN_API:
            fail_collect(messages, f"{label}: targetSdkVersion = {value}, but "
                                   f"Google Play rejects anything below "
                                   f"{PLAY_MIN_API} (Android 16) for new apps "
                                   "and updates since 31 Aug 2026. "
                                   "buildozer.spec's android.api did not reach "
                                   "the manifest.")

    domain = spec_keys.get("package.domain", "")
    pkg_name = spec_keys.get("package.name", "")
    if domain and pkg_name:
        expected = f"{domain}.{pkg_name}"
        if name != expected:
            fail_collect(messages, f"{label}: application id is {name} but "
                                   f"buildozer.spec says {expected}. Play pins "
                                   "an app to its id forever, so a mismatch "
                                   "means the wrong app would be registered.")

    wanted_code = spec_keys.get("android.numeric_version", "")
    if wanted_code and version_code != wanted_code:
        fail_collect(messages, f"{label}: versionCode is {version_code} but "
                               f"buildozer.spec's android.numeric_version is "
                               f"{wanted_code}.")

    if not icons:
        fail_collect(messages, f"{label}: no application-icon entries in the "
                               "manifest, so the launcher falls back to the "
                               "stock Android icon.")


def main(argv):
    if len(argv) < 2:
        print("usage: verify_play_ready_artifact.py <directory> [<directory> ...]")
        return 2

    spec_keys, err = read_spec_keys(pathlib.Path("buildozer.spec"))
    if err:
        print(f"::error::{err}")
        return 1

    apks = []
    for arg in argv[1:]:
        base = pathlib.Path(arg)
        if base.is_dir():
            apks.extend(sorted(base.glob("*.apk")))
        elif base.suffix == ".apk":
            apks.append(base)
    if not apks:
        print("::error::no .apk found to check")
        return 1

    aapt = find_aapt()
    if not aapt:
        print("::error::aapt not found in the Android SDK build-tools")
        return 1
    print(f"aapt: {aapt}")

    messages = []
    for apk in apks:
        check_apk(aapt, apk, spec_keys, messages)

    if messages:
        print("::error::Play readiness check failed")
        for message in messages:
            print(f"::error::{message}")
        return 1

    print("Play readiness OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
