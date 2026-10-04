"""Delete a cached p4a dist that was rendered for a different targetSdkVersion.

python-for-android decides whether to reuse an existing distribution by
looking only at the requirements, the bootstrap and the architecture
("Of the existing distributions, the following meet the given requirements").
It never compares ``android.api``.  The Gradle project in that dist was
rendered from ``build.tmpl.gradle`` once, at creation time, with whatever
``android.api`` was current then - so restoring it from the Actions cache
after raising ``android.api`` silently keeps building the *old* target SDK.

Google Play refuses such an upload, so drop the dist and let p4a re-render it.
Recipe builds and the NDK live next to ``dists/``, not inside it, so this
throws away seconds rather than the whole cache.
"""

import pathlib
import re
import shutil
import sys

SPEC = pathlib.Path("buildozer.spec")
BUILD_ROOT = pathlib.Path(".buildozer") / "android" / "platform"

# What build.tmpl.gradle writes: compileSdkVersion / targetSdkVersion.
SDK_LEVEL = re.compile(
    r"\b(?:targetSdkVersion|compileSdkVersion|targetSdk|compileSdk)\b"
    r"\D{0,12}(\d+)")


def read_api(path):
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return None, f"cannot read {path}: {exc}"
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped[0] in "#;":
            continue
        key, sep, value = stripped.partition("=")
        if sep and key.strip() == "android.api":
            try:
                return int(value.strip()), None
            except ValueError:
                return None, f"android.api is not an integer: {value.strip()!r}"
    return None, "buildozer.spec has no active android.api"


def main():
    if not SPEC.exists():
        print("::error::buildozer.spec not found")
        return 1

    api, err = read_api(SPEC)
    if err:
        print(f"::error::{err}")
        return 1

    print(f"buildozer.spec android.api = {api}")

    if not BUILD_ROOT.exists():
        print("no cached Android build tree, nothing to check")
        return 0

    dists = sorted(p for p in BUILD_ROOT.glob("build-*/dists/*")
                   if p.is_dir())
    if not dists:
        print("no cached distributions, nothing to check")
        return 0

    dropped = 0
    for dist in dists:
        gradle = dist / "build.gradle"
        if not gradle.exists():
            hits = [p for p in dist.rglob("build.gradle")]
            gradle = hits[0] if hits else None

        if gradle is None:
            print(f"dropping {dist}: no build.gradle to verify")
            shutil.rmtree(dist, ignore_errors=True)
            dropped += 1
            continue

        try:
            text = gradle.read_text(encoding="utf-8-sig", errors="replace")
        except OSError as exc:
            print(f"dropping {dist}: cannot read {gradle}: {exc}")
            shutil.rmtree(dist, ignore_errors=True)
            dropped += 1
            continue

        levels = sorted({int(v) for v in SDK_LEVEL.findall(text)})
        if not levels:
            print(f"dropping {dist}: {gradle} declares no SDK level, so the "
                  "target SDK cannot be trusted")
            shutil.rmtree(dist, ignore_errors=True)
            dropped += 1
        elif any(level != api for level in levels):
            print(f"dropping {dist}: {gradle} says {levels} but buildozer.spec "
                  f"wants {api}. p4a reuses this dist unchanged, so the next "
                  "build would ship the stale targetSdkVersion.")
            shutil.rmtree(dist, ignore_errors=True)
            dropped += 1
        else:
            print(f"keeping  {dist}: {gradle} already targets {api}")

    print(f"{dropped} stale distribution(s) removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
