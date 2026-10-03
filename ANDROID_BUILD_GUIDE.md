# Building **Sky Strikers** into an Android APK (Pygame + Buildozer)

A complete, verified path from `main.py` to an installable `.apk` you can sideload
onto a phone or publish to Google Play.

---

## 0. What you have

```
game/
├── main.py                      <- the entire game (pygame, sys, random only)
├── buildozer.spec               <- packaging config (already filled in)
├── p4a-recipes/
│   └── pygame-ce/
│       └── __init__.py          <- custom recipe that cross-compiles pygame
├── .github/workflows/
│   ├── build-debug-apk.yml      <- cloud debug APK build (no Linux needed)
│   └── build-release-apk.yml    <- cloud signed APK + .aab on a v* tag
└── ANDROID_BUILD_GUIDE.md       <- this file
```

**Before you build anything, run the game on your PC:**

```bash
pip install pygame
python main.py
```

If it runs on your desktop, it will run on the phone — same interpreter, same
library. The APK step is pure packaging.

---

## 1. Understand the toolchain (read this once)

| Piece | What it does |
|---|---|
| **python-for-android (p4a)** | Cross-compiles CPython + your C extensions for ARM. Downloads its own SDK/NDK. |
| **Buildozer** | A friendly front-end that reads `buildozer.spec`, runs p4a, calls Gradle, and hands you an `.apk`. |
| **Gradle** | Google's build system. Compiles the Java/Manifest wrapper and packages the APK. |
| **Bootstrap** | Which native shell the app runs in. Pygame needs the **`sdl2`** bootstrap: it starts SDL2, then runs your `main.py`. |
| **Recipe** | Instructions for p4a on how to build one native library. Pygame is not built-in in a usable state, so we ship our own recipe. |

The chain is:

```
main.py  ->  p4a (CPython 3.11 + pygame for arm64)  ->  Gradle  ->  app-debug.apk
```

### Hard requirement: the build host must be Linux or macOS

Buildozer **cannot run on native Windows.** It shells out to GNU tools
(`patch`, `autoconf`, `make`, shell scripts). You have three options:

| Option | Difficulty | Notes |
|---|---|---|
| **WSL2** (Windows 10/11) | Easy | Recommended on Windows. Real Ubuntu, no VM needed. |
| **Linux / macOS** | Easiest | Native, fastest, best for CI. |
| **Docker** | Medium | Most reproducible. Works on Windows/macOS/Linux identically. |

### 1a. No Linux on this machine? Build it in the cloud

If installing WSL or Docker feels like a chore, there is a third option that
needs **nothing installed at all**: two GitHub Actions workflows are already
included. GitHub builds the APK on a free Ubuntu runner and hands it back as a
downloadable file.

```
.github/workflows/build-debug-apk.yml     -> every push: a playable debug APK
.github/workflows/build-release-apk.yml   -> on a v* tag: a signed APK + .aab
```

**To use them, no command line needed:**

1. Go to <https://github.com/new> and create an **empty** repository (do not
   tick "add a README").
2. On the new repo's page click **uploading an existing file**.
3. Drag the whole `game` folder in — including the hidden `.github` folder.
   (If the browser refuses, first create a `.github` placeholder: in the GitHub
   web editor type a filename `a.txt`, then rename it to `.github/keep`.)
4. Click the **Actions** tab. A "Build debug APK" run has already started.
5. Wait 25–40 min for the first run. Click the run, scroll to **Artifacts**,
   download `skystrikers-debug-apk`, unzip, install the `.apk` on your phone.

Every later push rebuilds in ~5 minutes, and the SDK/NDK cache is reused.

With the GitHub CLI or git installed the same thing is one command:

```bash
git init && git add . && git commit -m "Sky Strikers"
gh repo create skystrikers --public --source=. --push
```

The first run is slow because it downloads ~4 GB (Android SDK, NDK, CMake,
CPython sources) and compiles Python + SDL for each ABI. Be patient.

### 1b. Signing a real release (cloud)

The release workflow needs an upload keystore, which you create **once** on
any machine — PowerShell is fine:

```powershell
keytool -genkey -v -keystore skystrikers.keystore -alias skystrikers `
        -keyalg RSA -keysize 2048 -validity 10000

[Convert]::ToBase64String([IO.File]::ReadAllBytes("skystrikers.keystore")) |
  Set-Clipboard
```

Add that clipboard content as the repository secret `KEYSTORE_BASE64`, plus
`KEYSTORE_PASSWORD`, `KEY_ALIAS`, `KEY_ALIAS_PASSWORD`
(**Settings → Secrets and variables → Actions**). Then push a tag:

```bash
git tag v1.0.0 && git push origin v1.0.0
```

The signed `.apk` and the Play Store `.aab` are attached to the release page.
To build without publishing anything, run the workflow by hand instead
(**Actions → Build signed release APK / AAB → Run workflow**); the signed
files are then just an artifact, kept for 90 days.
**Back the keystore file up** — lose it and you can never update the app on
the Play Store again.

---

## 2. Set up the build machine

### 2a. Windows → WSL2 (recommended for Windows users)

```powershell
wsl --install -d Ubuntu-22.04
```

Reboot, open **Ubuntu**, create your user, then inside WSL:

```bash
sudo apt update && sudo apt upgrade -y
```

> **Why Ubuntu 22.04?** Its default Python is 3.10, which every recipe supports.
> 24.04 ships 3.12, and Python 3.12+ removed `distutils`, which breaks the
> host-python and SDL recipes. If you insist on 24.04, use the `uv` trick in
> section 3 to get an isolated Python 3.11 — everything else is identical.

**Keep your project inside the WSL filesystem** (`~/games/skystrikers`), *not*
on `/mnt/c/...`. Building from a Windows-mounted drive is 5–10x slower and
occasionally breaks on file permissions.

### 2b. System packages

```bash
sudo apt install -y \
    git zip unzip openjdk-17-jdk python3-pip python3-venv \
    build-essential autoconf automake libtool pkg-config cmake ccache \
    libffi-dev libssl-dev zlib1g-dev \
    libncurses5-dev libncursesw5-dev libtinfo5 \
    patch gettext
```

**Ubuntu 24.04 notes:** `libncurses5-dev` was dropped; install
`libncurses-dev` instead. `libtinfo5` may need the `universe` repo
(`sudo add-apt-repository universe`) — if `libtinfo5` cannot be found, just
drop it from the list; it is only a convenience.

Verify Java (must be 17 for current Gradle):

```bash
java -version     # expect: openjdk version "17.x"
```

### 2c. (Optional but recommended) An isolated Python 3.11

Buildozer and p4a are far happier on Python 3.10/3.11. If your default Python
is 3.12+, grab a standalone 3.11 with [`uv`](https://docs.astral.sh/uv/) —
it works on every distro and needs no root:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

### 2d. Create a virtualenv

> **Never install buildozer system-wide.** A distro `python3-buildozer` upgrade
> will break your toolchain halfway through a 20-minute compile.

```bash
mkdir -p ~/games/skystrikers
cd ~/games/skystrikers

# Option 1 - with uv (recommended, gives you Python 3.11 automatically)
uv venv --python 3.11 .venv
source .venv/bin/activate

# Option 2 - with the system Python 3.10
python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip wheel setuptools
pip install buildozer "cython==3.0.11" virtualenv
```

**Pins that matter:**

* `cython==3.0.11` — the exact version `p4a-recipes/pygame-ce` pins into the
  hostpython, and the one this project builds with in CI. pygame-ce's
  `setup.py` imports Cython on every `build_ext` run; without it the build
  dies in seconds with `You need cython. https://cython.org/`. Do **not**
  downgrade to `cython<3.0`: pygame-ce's own `pyproject.toml` declares
  `cython<=3.0.11`, and the older pin is what breaks `longintrepr.h`.
* `--upgrade pip wheel setuptools` — old pip/setuptools break PEP 517 builds.

Check what you got:

```bash
python -c "import sys; print(sys.version)"   # want 3.10.x or 3.11.x
buildozer --version
```

---

## 3. Drop the project in and configure

Copy `main.py`, `buildozer.spec` and the `p4a-recipes/` folder into
`~/games/skystrikers/`, then confirm the layout:

```bash
cd ~/games/skystrikers
ls
# buildozer.spec  main.py  p4a-recipes

cat buildozer.spec | grep -E "requirements|p4a.branch|p4a.local_recipes|android.archs|orientation"
```

You should see:

```ini
requirements = python3==3.11.15,hostpython3==3.11.15,pygame-ce
p4a.branch = develop
p4a.local_recipes = ./p4a-recipes
android.archs = arm64-v8a
orientation = portrait
```

If you never ran `buildozer init`, you can skip it — the supplied
`buildozer.spec` is complete.

### What each non-obvious spec line does

| Setting | Why this value |
|---|---|
| `requirements = python3==3.11.15,hostpython3==3.11.15,pygame-ce` | `pygame-ce` is our local recipe; it still installs the `pygame` module name, so your code is unchanged. Python is pinned because 3.12+ breaks the host build, and **`hostpython3` must carry the identical version** — see the row below. |
| `p4a.branch = develop` | The upstream `pygame` recipe is frozen at pygame **2.1.0** (2021) on *both* `master` and `develop`. `develop` is the actively maintained branch, so we use it plus our local recipe to get pygame-ce 2.5.2. |
| `p4a.local_recipes = ./p4a-recipes` | Tells p4a where to find `p4a-recipes/pygame-ce/__init__.py`. **Commenting this line out is the single most common way to break the build** — p4a silently falls back to its unbuildable `pygame` 2.1.0 recipe. |
| `p4a.bootstrap = sdl2` | Pygame runs inside SDL2. Without this you get the Kivy bootstrap and a blank screen. |
| `android.entrypoint = org.kivy.android.PythonActivity` | Despite the name, this is correct: the SDL2 bootstrap initialises SDL2 and then executes `main.py`. |
| `android.archs = arm64-v8a` | 64-bit covers every phone since ~2016 and roughly halves build time. Add `armeabi-v7a` (comma separated) for 32-bit only if you still support Android devices from before ~2016; add `x86_64` only for emulators. |
| `android.api = 33`, `android.minapi = 24`, `android.ndk_api = 24` | Target Android 13, run on Android 7.0+. `ndk_api` **must** equal `minapi` — a mismatch is rejected by p4a. |
| `android.ndk = 25b` | NDK r25b is the best-tested version for p4a. r26+ changes libc headers and causes link errors. |
| `orientation = portrait` + `android.manifest.orientation = portrait` | Locks the game upright — without the second line Android may still rotate the Activity. |
| `fullscreen = 1` | Immersive fullscreen: no status bar, no nav bar, no notch letterbox. |
| `android.wakelock = True` | Keeps the screen on mid-game (requires the `WAKE_LOCK` permission, already listed). |
| `android.allow_backup = True` | Harmless for a game; set `False` if you ever add saved data. |
| `android.release_artifact = apk` | Change to `aab` when you publish to Google Play. |
| `source.exclude_*` | Keeps `.buildozer/`, tests and the recipe sources out of the APK. The APK only needs `main.py`. |

---

### 3.1 The local pygame-ce recipe (what `p4a-recipes/` is for)

python-for-android *does* ship a `pygame` recipe, but it is pinned to
**pygame 2.1.0 (2021)** on both its `master` and `develop` branches and it does
not build against current NDKs or Python versions. So we override it with our
own 129-line recipe:

```
p4a-recipes/pygame-ce/__init__.py
```

`p4a.local_recipes = ./p4a-recipes` makes p4a look in that folder for recipes,
and `pygame-ce` in `requirements` selects ours instead of the built-in one.

What the recipe does, in order:

1. Downloads `pygame-ce 2.5.2` and unpacks it.
2. Reads pygame's own `buildconfig/Setup.Android.SDL2.in` — the template that
   lists which C modules to compile and which SDL2 libraries to link.
3. Substitutes the real paths for this build: the SDL2 include dir from the
   `sdl2` bootstrap, the `libpng`/`libjpeg` build dirs, and the versioned NDK
   lib dir. The result is written to `Setup`, and pygame's `setup.py` compiles
   the extensions from it.
4. Sets `USE_SDL2=1`, `PYGAME_CROSS_COMPILE=TRUE`, `PYGAME_ANDROID=TRUE`.

It installs into `site-packages/pygame`, so **your code still does
`import pygame`** — nothing in `main.py` changes.

Two details worth knowing if you edit it:

* `site_packages_name` **must** be `"pygame"` (the folder it installs into),
  even though the recipe is named `pygame-ce`. Set it to `pygame-ce` and the
  build "succeeds" but the app dies on `ModuleNotFoundError: pygame`.
* The template has 5 placeholders (`sdl_includes`, `sdl_ttf_includes`,
  `sdl_image_includes`, `sdl_mixer_includes`, `freetype_includes`). The recipe
  also passes two legacy ones (`jpeg_includes`, `png_includes`) which
  `str.format` simply ignores — harmless.

**Bumping pygame-ce:** change `version` on line 26 of the recipe. Confirm the
release exists at
<https://github.com/pygame-community/pygame-ce/releases> and that it still
ships `buildconfig/Setup.Android.SDL2.in`, then `buildozer appclean` and
rebuild. Any 2.4.x–2.5.x release works; `Setup.Android.SDL2.in` has been stable
across those.

### 3.2 Pre-flight check (run this before every build)

A wrong `buildozer.spec` does not fail where you made the mistake — it fails
~40 minutes later, deep inside python-for-android. This script checks the
whole packaging setup up front and takes under a second:

```bash
python3 .github/scripts/verify_packaging.py
```

It verifies that:

* `requirements` contains `pygame-ce`, not plain `pygame`
  (plain `pygame` selects the unbuildable pygame **2.1.0** recipe);
* `python3` and `hostpython3` are pinned to the **identical** version
  (p4a aborts otherwise, see kivy/buildozer#2040);
* `p4a.local_recipes` is present **and uncommented**;
* `p4a.branch = develop` and `p4a.bootstrap = sdl2`;
* the recipe parses, defines `version`, `name` and
  `site_packages_name = "pygame"`, and references no undefined names;
* `main.py` only imports `pygame`, `sys`, `random` and `os`.

CI runs the same script as the first step of both workflows, so a broken
config fails in seconds instead of burning a full build. Any non-zero exit
means do not start the build yet.

---

## 4. Build the debug APK

```bash
cd ~/games/skystrikers
buildozer -v android debug
```

**The first build takes 20–60 minutes** and downloads ~4 GB (Android SDK,
NDK, CMake, CPython sources). It compiles Python and SDL from scratch for each
ABI. Be patient, and keep the machine awake.

If you only want to sanity-check the toolchain before the real compile:

```bash
buildozer android sdk          # just download SDK + NDK
```

When it finishes you get:

```
bin/skystrikers-1.0-arm64-v8a-debug.apk
```

---

## 5. Install and debug on the phone

### Option 1 — let Buildozer do it (easiest)

```bash
buildozer android deploy run logcat
```

This installs over USB, launches the app, and streams `logcat`.

### Option 2 — copy the APK to the phone

Copy `bin/*.apk` to the phone and tap it. You must enable
**Settings → Apps → Special app access → Install unknown apps** for whatever
app opens it (Files / Chrome).

### Option 3 — adb

```bash
adb devices                       # phone must show up
adb install -r bin/*.apk
adb logcat | grep -i python       # see tracebacks live
adb shell am start -n org.yourstudio.skystrikers/.PythonActivity
```

### Useful commands

```bash
buildozer android clean           # wipe the APK, keep the SDK/NDK cache
buildozer appclean                # wipe EVERYTHING (re-downloads the SDK)
buildozer android debug -- --private-data-dir .p4a
```

**Rebuilds after the first one take 1–3 minutes** because the SDK, NDK,
CPython and SDL objects are cached. Iterate on `main.py` freely.

---

## 6. Release build (signed, for distribution)

Debug APKs are signed with p4a's throwaway debug keystore — fine for
sideloading, useless for Play Store. For a real release:

### 6a. Create an upload keystore (ONCE — back this file up)

```bash
keytool -genkey -v \
  -keystore ~/skystrikers.keystore \
  -alias skystrikers \
  -keyalg RSA -keysize 2048 -validity 10000
```

### 6b. Export the four `P4A_RELEASE_*` variables

Buildozer reads **no** `android.keystore*` key from `buildozer.spec` — those
lines are silently ignored. It looks only at four environment variables, and
if any is missing it prints `P4A_RELEASE_KEYSTORE is missing--sign will not be
passed`, drops `--sign`, and still exits 0:

```bash
export P4A_RELEASE_KEYSTORE=~/skystrikers.keystore
export P4A_RELEASE_KEYSTORE_PASSWD=yourpassword
export P4A_RELEASE_KEYALIAS=skystrikers
export P4A_RELEASE_KEYALIAS_PASSWD=yourpassword
```

All four must be exported in the **same shell** that runs `buildozer`.

> Buildozer's default for `debug` is p4a's throwaway keystore, which is what
> you sideload with. The block above is only for a real signed release.

### 6c. Build, then check that it really signed

```bash
buildozer -v android release
# -> bin/skystrikers-1.0-arm64-v8a-release.apk
```

The name matters: `*-release.apk` means `--sign` was passed,
`*-release-unsigned.apk` means the four variables did not reach buildozer.
Confirm the signature rather than trusting the name:

```bash
APKSIGNER="$(find ~/.buildozer/android/platform/android-sdk \
  -name apksigner -path '*build-tools*' -print -quit)"
"$APKSIGNER" verify --print-certs bin/skystrikers-1.0-arm64-v8a-release.apk
# V2 Signer: certificate SHA-256 digest: <your keystore's fingerprint>
```

CI runs the same check via `.github/scripts/verify_signed_artifacts.py` plus
`apksigner verify`, so an unsigned artifact fails the release job instead of
being published.

### 6d. Shrink the APK further

The spec already ships one ABI, which is the big win (~10 MB instead of
~20–30 MB for two). If you ever re-add `armeabi-v7a` and need it smaller
again, drop back to:

```ini
android.archs = arm64-v8a
```

### 6e. Google Play (App Bundle)

```ini
android.release_artifact = aab
```

```bash
buildozer android release
# -> bin/skystrikers-1.0-arm64-v8a-release.aab
```

Upload that `.aab` at <https://play.google.com/console>.

---

## 7. Icons and splash screen

Buildozer uses a default icon unless you point it at your own.

```bash
pip install pillow
# 512x512 PNG for the launcher icon
python - <<'PY'
from PIL import Image, ImageDraw
img = Image.new("RGBA", (512, 512), (10, 12, 34, 255))
d = ImageDraw.Draw(img)
d.polygon([(256, 90), (400, 400), (256, 330), (112, 400)], fill=(108, 232, 255))
d.ellipse((226, 170, 286, 250), fill=(255, 214, 92))
img.save("icon.png")
PY
```

Then uncomment in `buildozer.spec`:

```ini
icon.filename = %(source.dir)s/icon.png
#icon.adaptive_foreground.filename = %(source.dir)s/icon_fg.png   # Android 8+
#icon.adaptive_background.filename = %(source.dir)s/icon_bg.png
#presplash.filename = %(source.dir)s/presplash.png                # 1024x1024
#android.presplash_color = #0A0C22
```

`.png` is already in `source.include_exts`, so no other change is needed.

---

## 8. Docker build (optional, most reproducible)

If your host is messy — or you are on Windows/macOS and do not want WSL —
build inside a container. Reproducible on any OS.

`Dockerfile`:

```dockerfile
FROM python:3.11-slim

ENV USER=user HOME_DIR=/home/user DEBIAN_FRONTEND=noninteractive
ENV PATH=$HOME_DIR/.local/bin:$PATH LANG=en_US.UTF-8

RUN apt-get update -qq && apt-get install -qq -y --no-install-recommends \
    locales git zip unzip sudo patch autoconf automake libtool build-essential \
    ccache cmake gettext pkg-config libffi-dev libssl-dev zlib1g-dev \
    libncurses5-dev libtinfo5 openjdk-17-jdk \
 && locale-gen en_US.UTF-8 \
 && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash $USER \
 && echo "%sudo ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

USER $USER
RUN pip install --no-cache-dir buildozer "cython==3.0.11" virtualenv
WORKDIR /home/user/project
ENTRYPOINT ["buildozer"]
```

`build.sh`:

```bash
#!/usr/bin/env bash
set -e
mkdir -p cache/buildozer cache/gradle
docker build -t skystrikers-build .

docker run --rm -u "$(id -u):$(id -g)" \
  -v "$PWD":/home/user/project \
  -v "$PWD/cache/buildozer":/home/user/.buildozer \
  -v "$PWD/cache/gradle":/home/user/.gradle \
  skystrikers-build -v android debug

ls -lh bin/
```

`cache/` keeps the SDK/NDK between builds, so only the first run is slow.

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `buildozer: command not found` on Windows | Buildozer needs Linux | Use WSL2 or Docker |
| `Aidl not found` / `aidl` crash | Android SDK build-tools too new for p4a | `buildozer android clean`, or pin `android.ndk = 25b` and delete `.buildozer/android/platform/build-*` |
| `fatal error: longintrepr.h: No such file` | Cython newer than the version the recipe pins | Install `cython==3.0.11` (the same pin `p4a-recipes/pygame-ce` uses) and `buildozer appclean`. Do not swap in `cython<3.0` — pygame-ce is built and tested against `cython<=3.0.11` |
| `ModuleNotFoundError: No module named 'distutils'` | Python 3.12+ | Pin `requirements = python3==3.11.15,...` and use a 3.11 venv |
| `Recipe not found: pygame-ce` | Local recipes path wrong | `p4a.local_recipes = ./p4a-recipes`, and the file must be `p4a-recipes/pygame-ce/__init__.py` |
| Build dies compiling **`pygame-2.1.0`** (or any 15-minute-old `pygame` download) | `requirements` says plain `pygame`, **or** `p4a.local_recipes` is commented out | p4a then uses its built-in recipe, pinned to pygame 2.1.0. Restore `requirements = python3==3.11.15,hostpython3==3.11.15,pygame-ce` and an active `p4a.local_recipes = ./p4a-recipes`, then `buildozer appclean` |
| `python3 should have same version as hostpython3, 3.11.15 != 3.14.2` | `hostpython3` is unpinned, so p4a takes its own default (3.14.2) while `python3` is pinned | p4a's `hostpython3` recipe hardcodes 3.14.2 and aborts on any mismatch. Pin **both** to the same version: `python3==3.11.15,hostpython3==3.11.15`. See kivy/buildozer#2040 — the `kivy/buildozer:latest` image moved to Ubuntu 26.04 / Python 3.14, so this now trips everyone who pins `python3` |
| `NameError: name 'ndk_lib' is not defined` (or similar) inside the recipe | Undefined name in `p4a-recipes/` | Run `python3 .github/scripts/verify_packaging.py` — it parses the recipe and reports undefined names before you build |
| `You need cython. https://cython.org/, pip install cython --user` | pygame-ce's `setup.py` imports Cython at module level for *every* `build_ext` run | The recipe puts `cython==3.0.11` in `hostpython_prerequisites`, which p4a pip-installs into the hostpython right before `build_ext`. Confirm that line is still there, then `buildozer appclean` |
| `KeyError: 'project'` in `buildconfig/get_version.py` | The recipe replaced all of `pyproject.toml` instead of only its `[build-system]` table | `buildconfig.get_version` reads `conf["project"]["version"]`, so `[project]` must survive the rewrite. `verify_packaging.py` fails the build if it is stripped |
| `ModuleNotFoundError: No module named 'buildconfig'` while building pygame-ce | pip's plain `setuptools.build_meta` backend does not put the source directory on `sys.path` | The recipe must select `setuptools.build_meta:__legacy__` — only the legacy backend runs `setup.py` with the project directory importable |
| pygame-ce build invokes **meson**, or dies inside `pip install .` | pygame-ce's own `pyproject.toml` names `meson-python`, which ignores the generated `Setup` and cannot cross compile with our NDK env | The recipe rewrites `[build-system]` to setuptools in `prebuild_arch`. `verify_packaging.py` feeds a realistic meson `pyproject.toml` through the recipe and fails if meson survives |
| `'Context' object has no attribute 'has_recipe'` (or `get_include_dirs`) inside the recipe | p4a's `Context` exposes only `has_lib()`/`has_package()`; `get_include_dirs()` exists only on `sdl2_image` and `sdl2_mixer` | `verify_packaging.py` runs `prebuild_arch()` against a stub that reproduces p4a's real API, so this fails in seconds rather than minutes into a cold build |
| CI fails in **seconds** at `Verify packaging configuration` | Deliberate | The message tells you exactly which of the settings above is wrong. Fix it rather than re-running the build |
| `No module named 'Setup'` / buildconfig error | Recipe ran before sources unpacked | `buildozer appclean` (full wipe) and rebuild |
| App installs, **black screen** | Wrong bootstrap or missing SDL2 | `p4a.bootstrap = sdl2`; confirm `requirements` contains `pygame-ce` |
| App installs, **black screen**, config is correct | `pygame.SCALED` unsupported by that GPU/driver | Set `SCALED_DISPLAY = False` in `main.py` and rebuild — the game falls back to software scaling automatically |
| App installs, **crashes instantly** | Missing shared lib | `adb logcat \| grep -i "error\|dlopen\|python"` — usually an ABI mismatch; try `android.archs = arm64-v8a` only |
| **Touch does not work** | Buttons need finger events, not mouse | This game handles `FINGERDOWN/FINGERUP` *and* mouse. If only mouse works, SDL touch emulation is off — set `fullscreen = 0`, run once, and re-enable |
| Buttons in the **wrong place** | Screen aspect/letterboxing | The game maps screen→virtual coordinates itself; if you changed `VW, VH` re-test, the mapping is automatic |
| High score **not remembered** after closing the app | `skystrikers.save` could not be written | It is written to the app's private folder, so this is normal and needs no permission. If it fails the game silently plays without a record. Deleting the app data clears it. |
| Game runs but **is letterboxed with big black bars** | Device aspect differs from 480×800 | Expected and correct. Reduce `VW, VH` in `main.py` to match your device ratio |
| **`Gradle build failed`** / `Unsupported class file major version` | Wrong JDK | Install **JDK 17**, remove JDK 21 from the path |
| `Permission denied: '/root/.buildozer'` | Running as root | Buildozer refuses root; use a normal user (or Docker) |
| Build is **extremely slow** | Project on `/mnt/c` (WSL) | Move the project to `~/` |
| `Buildozer` hangs on "Downloading" | Network/proxy | Set `export HTTP_PROXY=...`, or pre-download with `buildozer android sdk` |
| Want to **see Python tracebacks** | logcat filters | `buildozer android deploy run logcat` then `adb logcat -s python:*` |
| SDL_mixer licence warning during build | SDL2_mixer recipe | Harmless warning — the game still works |
| `pygame.freetype` missing | Not built by the Android recipe | Expected. Use `pygame.font` (this game does) |

### Nuclear option

```bash
rm -rf .buildozer bin
buildozer -v android debug
```

Costs you a full SDK/NDK re-download, but always fixes "stale build state"
problems.

---

## 10. Mobile performance notes

The game holds **60 fps with room to spare** (measured headless, one state per
process so the numbers are trustworthy; 16.7 ms is the 60 fps budget):

| Screen | `SCALED_DISPLAY = True` | software fallback |
|---|---|---|
| menu | 2.3 ms | 4.6 ms |
| combat | 2.9 ms | 4.5 ms |
| pause | 2.6 ms | 4.5 ms |
| game over | 3.2 ms | 4.7 ms |

How it stays fast:

* **The upscale is the driver's job, not the CPU's.** `SCALED_DISPLAY = True`
  asks SDL2 for a `pygame.SCALED` window, so SDL2 stretches the 480×800 canvas
  to the real screen. Doing that stretch in software with
  `pygame.transform.scale` costs about **8 ms per frame** on a 1080×1920
  screen — roughly half the entire frame budget. If the driver refuses
  `pygame.SCALED`, the game silently falls back to the software path, so this
  is safe to leave on. **If a device ever shows a black screen, set
  `SCALED_DISPLAY = False` in `main.py` and rebuild.**
* **Fixed virtual resolution.** All game logic happens at 480×800, so the game
  looks identical on a 720p phone and a 1440p flagship (letterboxed if the
  aspect ratio differs).
* **Delta-time everywhere.** `dt` is clamped to 1/20 s so a hitch can never
  teleport an enemy through the player.
* **All sprites pre-rendered once.** Jets, flames and bullets are
  `convert()`ed at startup; nothing is drawn from scratch each frame.
* **Zero Surface allocations in the draw loop.** The menu/pause/game-over
  overlays, the control pad, the menu jets' bank angles and the game-over title
  zoom are all built once. Caching the full-screen overlays alone was worth
  **2 ms per frame** (a 480×800 SRCALPHA allocate+fill costs ~2 ms).
* **Audio is synthesised in the mixer's real format.** `pygame.mixer` is free
  to refuse the 22050 Hz mono format you ask for — on many systems it stays at
  44100 Hz stereo — so the tones are always built to match whatever
  `pygame.mixer.get_init()` reports. Hardcoding a rate makes every sound play
  at double speed and double pitch.
* **Hard caps.** `MAX_PARTICLES = 420`, `MAX_ENEMIES = 16` keep the worst case
  bounded on cheap hardware.
* **No external assets.** Sprites, sounds and the HUD are generated in code, so
  the APK is dominated by CPython + SDL, not your art.

### Saving data

The best score and best wave go to `skystrikers.save` in the working directory.
On Android that is the app's own private folder, so **no storage permission is
needed** and it is removed when the app is uninstalled. The game only uses the
`open` builtin, so the "pygame / sys / random only" rule still holds. Every
read and write is wrapped in a try/except — a read-only filesystem just means
no record, never a crash.

Things to do if you extend the game:

* Keep using `convert()` / `convert_alpha()` on anything created at runtime.
* Never create a `Surface` inside the update/draw loop.
* Pre-render text if you render it every frame.
* Set `SOUND_ENABLED = False` to drop audio if a device struggles.
* Set `FULLSCREEN = False` in `main.py` to get a resizable desktop window.

---

## 11. Quick reference

```bash
# desktop test
python main.py

# --- no local Linux needed: let GitHub build it ---
#   push the folder to a GitHub repo, then open the Actions tab
#   and download the "skystrikers-debug-apk" artifact

# first build (slow)
buildozer -v android debug

# rebuild after edits (fast)
buildozer android debug deploy run logcat

# release - export the four P4A_RELEASE_* variables first (section 6b),
# otherwise buildozer skips signing and you get a *-release-unsigned.apk
buildozer -v android release

# Play Store bundle
#   set android.release_artifact = aab first
buildozer -v android release

# clean
buildozer android clean      # keep caches
buildozer appclean           # nuke everything
```

### Useful links

* python-for-android docs — <https://python-for-android.readthedocs.io>
* Buildozer docs — <https://buildozer.readthedocs.io>
* p4a recipes list — <https://github.com/kivy/python-for-android/tree/develop/pythonforandroid/recipes>
* The SDL2 setup template this recipe depends on —
  <https://github.com/pygame-community/pygame-ce/blob/main/buildconfig/Setup.Android.SDL2.in>
* pygame-ce releases — <https://github.com/pygame-community/pygame-ce/releases>
* Fastest way to *play-test* before any build: **Pydroid 3** (Android) or
  **Termux + `pip install pygame`**, which runs the same script natively.
