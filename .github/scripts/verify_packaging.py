"""Minimal packaging sanity check before a long Buildozer run.

Checks that the buildozer.spec has the bare minimum needed for a
successful pygame APK build using p4a's built-in pygame recipe.
"""

import ast
import builtins
import pathlib
import re
import struct
import sys

# ``os`` is stdlib and always present on Android.
ALLOWED_IMPORTS = {"pygame", "sys", "random", "os"}

errors = []


def fail(message):
    errors.append(message)


def read(path):
    return path.read_text(encoding="utf-8-sig")


def active_keys(text):
    """Return {key: [values]} for lines that are not commented out."""
    keys = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped[0] in "#;":
            continue
        key, sep, value = stripped.partition("=")
        if sep:
            keys.setdefault(key.strip(), []).append(value.strip())
    return keys


def check_spec():
    path = pathlib.Path("buildozer.spec")
    if not path.exists():
        fail("buildozer.spec is missing from the repository root.")
        return {}

    keys = active_keys(read(path))

    def require(key, why):
        values = keys.get(key, [])
        if not values:
            fail(f"buildozer.spec: '{key}' is missing or commented out. {why}")
            return ""
        return values[0]

    requirements = require(
        "requirements",
        "It must include 'python3' and a pygame requirement.",
    )
    if requirements and "pygame" not in requirements:
        fail(
            f"buildozer.spec: 'requirements' must contain 'pygame' (or 'pygame-ce'), "
            f"got '{requirements}'."
        )

    bootstrap = keys.get("p4a.bootstrap", [""])[0]
    if bootstrap and bootstrap != "sdl2":
        fail(f"buildozer.spec: p4a.bootstrap must be 'sdl2', got '{bootstrap}'.")

    if "android.accept_sdk_license" not in keys:
        fail(
            "buildozer.spec: 'android.accept_sdk_license = True' is missing, "
            "so the Android SDK install will hang on a licence prompt."
        )

    return keys


def check_main():
    path = pathlib.Path("main.py")
    if not path.exists():
        fail("main.py is missing from the repository root.")
        return

    try:
        tree = ast.parse(read(path))
    except SyntaxError as exc:
        fail(f"main.py has a syntax error: {exc}")
        return

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])

    extra = sorted(imported - ALLOWED_IMPORTS)
    if extra:
        fail(
            f"main.py imports outside the allowed set {sorted(ALLOWED_IMPORTS)}: "
            f"{extra}. The APK must stay pure pygame with no extra wheels."
        )


def main():
    keys = check_spec()
    check_main()

    if errors:
        print("::error::Packaging configuration check failed")
        for message in errors:
            print(f"::error::{message}")
        return 1

    print("Packaging configuration OK:")
    for key in (
        "requirements",
        "p4a.bootstrap",
        "p4a.branch",
        "p4a.local_recipes",
        "android.api",
        "android.minapi",
        "android.ndk_api",
        "android.ndk",
        "android.archs",
        "orientation",
        "fullscreen",
    ):
        values = keys.get(key)
        if values:
            print(f"  {key} = {values[0]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
