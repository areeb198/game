"""Fail fast on packaging mistakes before a 40 minute Buildozer run.

python-for-android ships its own ``pygame`` recipe pinned to pygame 2.1.0
(2021), which does not compile against NDK r25b.  The only way the APK can
build is from our local recipe in ``p4a-recipes/pygame-ce``, which p4a only
finds when ``p4a.local_recipes`` is active in ``buildozer.spec``.

This script checks that the configuration is actually wired up, so that a
bad change fails in seconds with a message instead of deep inside p4a.
"""

import ast
import builtins
import pathlib
import sys

# ``os`` is stdlib and always present on Android - main.py uses it only to
# detect ANDROID_ARGUMENT/ANDROID_ROOT for fullscreen and cursor handling.
ALLOWED_IMPORTS = {"pygame", "sys", "random", "os"}

BUILTINS = set(dir(builtins)) | {"__file__", "__name__"}

errors = []


def fail(message):
    errors.append(message)


def read(path):
    # utf-8-sig: Windows editors add a BOM. Python tolerates it in source
    # files, so refusing it here would be a false failure.
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


def check_python_pins(requirements):
    """python3 and hostpython3 must be pinned to the identical version.

    p4a's hostpython3 recipe hardcodes ``version = "3.14.2"`` and aborts in
    ``download()`` when python3 differs, which is exactly the failure the
    kivy/buildozer:latest image now triggers: that image moved to
    ubuntu:26.04 / Python 3.14, so an unpinned hostpython3 is 3.14.2 while a
    sane python3 pin is older. See kivy/buildozer#2040.
    """
    if not requirements:
        return

    pins = {}
    for part in requirements.split(","):
        part = part.strip()
        if not part:
            continue
        name, sep, version = part.partition("==")
        if sep:
            pins[name.strip()] = version.strip()

    target = pins.get("python3")
    if not target:
        fail("buildozer.spec: pin python3, e.g. 'python3==3.11.15'. Leaving it "
             "unpinned selects whatever p4a currently defaults to, which "
             "pygame-ce 2.5.x was never compiled against.")
        return

    host = pins.get("hostpython3")
    if host is None:
        fail("buildozer.spec: requirements must also carry "
             f"'hostpython3=={target}'. p4a's hostpython3 recipe defaults to "
             "3.14.2 and refuses to run when python3 is pinned elsewhere "
             "(error: python3 should have same version as hostpython3).")
    elif host != target:
        fail(f"buildozer.spec: hostpython3=={host} must equal python3=={target}"
             " - p4a aborts on any mismatch.")


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
        "It must read 'requirements = python3==3.11.15,hostpython3==3.11.15,pygame-ce'.",
    )
    if requirements and "pygame-ce" not in requirements:
        fail(
            "buildozer.spec: 'requirements' must contain 'pygame-ce', got "
            f"'{requirements}'. python-for-android's built-in 'pygame' recipe is "
            "pinned to pygame 2.1.0 and does not compile against NDK r25b."
        )

    check_python_pins(requirements)

    require(
        "p4a.local_recipes",
        "Without it p4a never loads p4a-recipes/pygame-ce/ and silently falls "
        "back to its broken built-in pygame recipe.",
    )

    require("p4a.branch", "It must be 'develop'.")

    bootstrap = keys.get("p4a.bootstrap", [""])[0]
    if bootstrap and bootstrap != "sdl2":
        fail(f"buildozer.spec: p4a.bootstrap must be 'sdl2', got '{bootstrap}'.")

    if "android.accept_sdk_license" not in keys:
        fail("buildozer.spec: 'android.accept_sdk_license = True' is missing, "
             "so the Android SDK install will hang on a licence prompt.")

    return keys


def check_recipe():
    path = pathlib.Path("p4a-recipes/pygame-ce/__init__.py")
    if not path.exists():
        fail("p4a-recipes/pygame-ce/__init__.py is missing. p4a has no "
             "pygame-ce recipe to build from.")
        return

    source = read(path)

    # Plain-text checks run before parsing so they still fire when the file
    # is syntactically broken and would otherwise swallow the real message.
    if 'name = "pygame-ce"' not in source:
        fail("Local recipe must declare name = \"pygame-ce\" (what you put in "
             "'requirements').")
    if 'site_packages_name = "pygame"' not in source:
        fail("Local recipe must declare site_packages_name = \"pygame\", or the "
             "wheel installs as site-packages/pygame-ce and 'import pygame' "
             "fails on the device.")
    if not any(line.strip().startswith("version =") for line in source.splitlines()):
        fail("Local recipe has no 'version' field, so p4a cannot build it.")

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        fail(f"Local recipe has a syntax error: {exc}")
        return

    undefined = undefined_names(tree)
    if undefined:
        fail("Local recipe references undefined name(s): "
             f"{', '.join(sorted(undefined))} - this raises NameError at build "
             "time, long after this file is first loaded.")


def undefined_names(tree):
    """Names read but never bound anywhere - pyflakes' F821, implemented
    in-tree so this check needs no extra dependency.

    Deliberately module-wide rather than scope-accurate: that can miss a
    bug across function boundaries but never invents one, so a red build
    always means a real problem.
    """
    bound = set(BUILTINS)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.Lambda)):
            if isinstance(node, ast.FunctionDef):
                bound.add(node.name)
            args = node.args
            bound.update(a.arg for a in args.args)
            bound.update(a.arg for a in args.kwonlyargs)
            bound.update(a.arg for a in args.posonlyargs)
            if args.vararg:
                bound.add(args.vararg.arg)
            if args.kwarg:
                bound.add(args.kwarg.arg)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ClassDef):
            bound.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bound.update(node.names)

    class Free(ast.NodeVisitor):
        def __init__(self):
            self.found = set()

        def visit_Name(self, node):
            if isinstance(node.ctx, ast.Load) and node.id not in bound:
                self.found.add(node.id)

    visitor = Free()
    visitor.visit(tree)
    return visitor.found


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
        fail(f"main.py imports outside the allowed set {sorted(ALLOWED_IMPORTS)}: "
             f"{extra}. The APK must stay pure pygame with no extra wheels.")


def main():
    keys = check_spec()
    check_recipe()
    check_main()

    if errors:
        print("::error::Packaging configuration check failed")
        for message in errors:
            print(f"::error::{message}")
        return 1

    print("Packaging configuration OK:")
    for key in (
        "requirements",
        "p4a.branch",
        "p4a.local_recipes",
        "p4a.bootstrap",
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
