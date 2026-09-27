[app]

# (str) Title of your application
title = Sky Strikers

# (str) Package name - becomes the app id, must be unique on the device
package.name = skystrikers

# (str) Package domain (needed for android packaging)
package.domain = org.yourstudio

# (str) Source code where the main.py lives
source.dir = .

# (list) File types copied into the APK from source.dir
source.include_exts = py,png,jpg,jpeg,ogg,wav,ttf

# (list) Never ship these - they bloat the APK massively
source.exclude_dirs = tests,test,bin,venv,.venv,.buildozer,__pycache__,git,docker

# (list) Patterns to exclude
source.exclude_patterns = *.pyc,*.pyo,*.md,buildozer.spec,p4a-recipes/*,*.spec,skystrikers.save

# (str) Application versioning (method 1)
version = 1.0

# (list) Application requirements.
#   python3  -> CPython for Android (pinned to 3.11: 3.12+ breaks several
#               recipes because distutils was removed)
requirements = python3,pygame-ce

# (str) Presplash of the application
#presplash.filename = %(source.dir)s/data/presplash.png

# (str) Icon of the application
#icon.filename = %(source.dir)s/data/icon.png

# (str) Adaptive icon (Android 8.0+)
#icon.adaptive_foreground.filename = %(source.dir)s/data/icon_fg.png
#icon.adaptive_background.filename = %(source.dir)s/data/icon_bg.png

# (list) Supported orientations - this game is portrait only
orientation = portrait

# (list) List of services to declare
#services = NAME:ENTRYPOINT_TO_PY,NAME2:ENTRYPOINT2_TO_PY

#
# OSX Specific
#

# (str) author = © Copyright Info
# (str) Kivy version for a macOS build (not used for the Android target)
#osx.kivy_version = 2.3.0

#
# Android specific
#

# (bool) Indicate if the application should be fullscreen or not.
# 1 = immersive fullscreen, no status bar, no nav bar -> what a game wants.
fullscreen = 1

# (string) Presplash background color
#android.presplash_color = #0A0C22

# (string) Presplash animation using Lottie format
#android.presplash_lottie = "path/to/lottie/file.json"

# (list) Permissions
# WAKE_LOCK is optional but recommended so the screen does not sleep mid-game.
android.permissions = android.permission.WAKE_LOCK

# (list) features (adds uses-feature -tags to manifest)
#android.features = android.hardware.touchscreen,android.hardware.gamepad

# (int) Target Android API, should be as high as possible.
android.api = 33

# (int) Minimum API your APK / AAB will support.
# 24 is required for modern Python 3 / SDL2 builds on Android
android.minapi = 24

# (int) Android NDK API to use. Must match android.minapi.
android.ndk_api = 24

# (str) Android NDK version to use (r25c is the sweet spot for p4a builds)
android.ndk = 25b

# (str) Android SDK / NDK directories (empty = buildozer downloads them)
#android.ndk_path =
#android.sdk_path =

# (bool) If True, then automatically accept SDK license agreements.
android.accept_sdk_license = True

# (str) Android entry point.
# The p4a SDL2 bootstrap boots SDL2 and then runs main.py, which is exactly
# what a pygame app needs - so the default Kivy-oriented activity is correct.
android.entrypoint = org.kivy.android.PythonActivity

# (str) Full name including package path of the Java class that implements
# the Android Activity
#android.activity_class_name = org.kivy.android.PythonActivity

# (str) Extra xml to write directly inside the <manifest> element
#android.extra_manifest_xml = ./src/android/extra_manifest.xml

# (str) Android app theme, default is ok for pygame games
#android.apptheme = "@android:style/Theme.NoTitleBar"

# (list) Pattern to whitelist for the whole project
#android.whitelist =

# (str) Path to a custom whitelist file
#android.whitelist_src =

# (str) Path to a custom blacklist file
#android.blacklist_src =

# (list) List of Java .jar files to add to the libs
#android.add_jars = foo.jar,bar.jar,path/to/more/*.jar

# (list) List of Java files to add to the android project
#android.add_src =

# (list) Android AAR archives to add
#android.add_aars =

# (list) Put these files or directories in the apk assets directory.
#android.add_assets =

# (list) Put these files or directories in the apk res directory.
#android.add_resources =

# (list) Gradle dependencies to add
#android.gradle_dependencies =

# (bool) Enable AndroidX support
#android.enable_androidx = True

# (list) add java compile options
#android.add_compile_options = "sourceCompatibility = 1.8", "targetCompatibility = 1.8"

# (list) Gradle repositories to add
#android.add_gradle_repositories =

# (list) packaging options to add
#android.add_packaging_options =

# (list) Java classes to add as activities to the manifest.
#android.add_activities = com.example.ExampleActivity

# (str) OUYA Console category
#android.ouya.category = GAME

# (str) Filename for your OUYA Console icon.
#android.ouya.icon.filename = %(source.dir)s/data/ouya_icon.png

# (str) XML file to include as an intent filters in <activity> tag
#android.manifest.intent_filters =

# (str) launchMode to set for the main activity.
#android.manifest.launch_mode = singleInstance

# (str) screenOrientation to set for the main activity.
# Valid values: portrait, landscape, sensor, userPortrait, fullSensor ...
android.manifest.orientation = portrait

# (list) Android additional libraries to copy into libs/
#android.add_libs_armeabi = libs/android/*.so
#android.add_libs_armeabi_v7a = libs/android-v7/*.so
#android.add_libs_arm64_v8a = libs/android-v8/*.so
#android.add_libs_x86 = libs/android-x86/*.so

# (bool) Indicate whether the screen should stay on.
# Needs WAKE_LOCK in android.permissions (set above).
android.wakelock = True

# (list) Android application meta-data to set (key=value format)
#android.meta_data =

# (str) Android library project to add
#android.library_references =

# (list) Android shared libraries to add to AndroidManifest.xml
#android.uses_library =

# (str) Android logcat filters to use
#android.logcat_filters = *:S python:D

# (bool) Android logcat only display log for the activity's pid
#android.logcat_pid_only = False

# (str) Android additional adb arguments
#android.adb_args = -H host.docker.internal

# (bool) Copy library instead of making a libpymodules.so
#android.copy_libs = 1

# (list) The Android archs to build for.
# arm64-v8a = 64-bit ARM (covers modern Android phones)
android.archs = arm64-v8a

# (int) overrides automatic versionCode computation
#android.numeric_version = 1

# (bool) enables Android auto backup feature
android.allow_backup = True

# (str) If you need to insert variables into your AndroidManifest.xml file,
# you can do so with the manifestPlaceholders property.
#android.manifest_placeholders = [myCustomUrl:"org.yourstudio.customurl"]

# (bool) Skip byte compile for .py files
# android.no-byte-compile-python = False

# (str) The format used to package the app for release mode (aab or apk).
# Use "aab" for Google Play, "apk" for direct sideloading.
android.release_artifact = apk

# (str) The format used to package the app for debug mode (apk or aar).
android.debug_artifact = apk

#
# Python for android (p4a) specific
#

# (str) python-for-android URL to use for checkout
#p4a.url =

# (str) python-for-android fork to use, defaults to upstream (kivy)
#p4a.fork = kivy

# (str) python-for-android branch to use.
# The pygame recipe only lives on the development branch, never on master.
p4a.branch = develop

# (str) python-for-android specific commit to use
#p4a.commit = HEAD

# (str) python-for-android git clone directory
#p4a.source_dir =

# (str) The directory in which python-for-android should look for your own
# build recipes. This is where ./p4a-recipes/pygame-ce/__init__.py lives.
p4a.local_recipes = ./p4a-recipes

# (str) Filename for the p4a hook
#p4a.hook =

# (str) Bootstrap to use for android builds.
# sdl2 is the bootstrap pygame needs (it starts SDL2, then runs main.py).
p4a.bootstrap = sdl2

# (int) port number to specify an explicit --port= p4a argument
#p4a.port =

# Control passing the --use-setup-py vs --ignore-setup-py to p4a
#p4a.setup_py = false

# (str) extra command line arguments to pass when invoking
# pythonforandroid.toolchain
#p4a.extra_args =

#
# iOS specific
#

# (str) Path to a custom kivy-ios folder
#ios.kivy_ios_dir = ../kivy-ios
ios.kivy_ios_dir = ../kivy-ios

# (str) Path to a custom certificate for code signing
#ios.codesign.allowed = false

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug with command output)
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1

# (str) Path to build artifact storage, absolute or relative to the spec file
# build_dir = ./.buildozer

# (str) Path to build output (i.e. .apk, .aab, .ipa) storage
# bin_dir = ./bin
