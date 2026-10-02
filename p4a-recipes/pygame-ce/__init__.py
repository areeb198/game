"""
Custom python-for-android recipe for SDL2-based pygame (pygame-ce).

python-for-android ships a `pygame` recipe, but it is pinned to pygame 2.1.0
(2021) on both its master and develop branches and does not build against
current NDKs / Python versions.  This local recipe points at pygame-ce 2.5.x,
which is a drop-in replacement (it still imports as `pygame`) and has an
up-to-date `buildconfig/Setup.Android.SDL2.in` for cross-compiling with the
NDK.

Drop this file at:   ./p4a-recipes/pygame-ce/__init__.py
and enable it in buildozer.spec with:

    p4a.branch = develop
    p4a.local_recipes = ./p4a-recipes
    requirements = python3==3.11.15,hostpython3==3.11.15,pygame-ce

`hostpython3` must carry the exact same version as `python3`: p4a's own
`hostpython3` recipe hardcodes 3.14.2 and aborts on any mismatch, and the
kivy/buildozer:latest image now ships Python 3.14, so an unpinned hostpython3
no longer happens to agree with a pinned python3 (kivy/buildozer#2040).
"""

from os.path import join

from pythonforandroid.recipe import CompiledComponentsPythonRecipe
from pythonforandroid.toolchain import current_directory


class PygameCeRecipe(CompiledComponentsPythonRecipe):
    """Recipe to build apps based on SDL2-based pygame."""

    version = "2.5.2"
    url = ("https://github.com/pygame-community/pygame-ce/archive/"
           "refs/tags/{version}.tar.gz")

    # The *recipe* is called pygame-ce (that is what you put in
    # `requirements`), but the wheel installs into site-packages/pygame, which
    # is the name your code imports.  site_packages_name MUST be "pygame" or
    # `import pygame` fails at runtime.
    name = "pygame-ce"
    site_packages_name = "pygame"

    depends = ["sdl2", "sdl2_image", "sdl2_mixer", "sdl2_ttf", "setuptools"]
    call_hostpython_via_targetpython = False   # setuptools is a host dep
    install_in_hostpython = False

    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)
        with current_directory(self.get_build_dir(arch.arch)):
            setup_template = open(
                join("buildconfig", "Setup.Android.SDL2.in")).read()

            # SDL2 comes from the bootstrap: headers under jni/, compiled
            # libs under libs/<arch>/.  Do not probe for these recipes -
            # Context has no has_recipe() (it exposes only has_lib() and
            # has_package()), so any such probe raises AttributeError.
            bootstrap = self.ctx.bootstrap.build_dir

            sdl_libs = [
                "-I" + join(bootstrap, "jni", "SDL", "include"),
                "-I" + join(bootstrap, "jni", "SDL2", "include"),
                "-L" + join(bootstrap, "libs", str(arch)),
            ]
            # Optional extra search dir for the NDK sysroot's own libs.
            ndk_lib = getattr(arch, "ndk_lib_dir_versioned", "")
            if ndk_lib:
                sdl_libs.append("-L" + ndk_lib)

            sdl_ttf_includes = " ".join([
                "-I" + join(bootstrap, "jni", "SDL2_ttf"),
                "-I" + join(bootstrap, "jni", "SDL_ttf"),
            ])

            # Only sdl2_image and sdl2_mixer define get_include_dirs() (both
            # are BootstrapNDKRecipe subclasses and both are in our depends).
            # sdl2 and sdl2_ttf do NOT define it - calling it there raises
            # AttributeError, so their headers are handled above via jni/.
            sdl_image_includes = "".join(
                f"-I{include_dir} "
                for include_dir in self.get_recipe(
                    "sdl2_image", self.ctx).get_include_dirs(arch))
            sdl_mixer_includes = "".join(
                f"-I{include_dir} "
                for include_dir in self.get_recipe(
                    "sdl2_mixer", self.ctx).get_include_dirs(arch))

            # jpeg_includes / png_includes exist only so this call stays
            # compatible with every pygame-ce 2.4.x-2.5.x template.  The
            # Android templates do not reference either placeholder, and
            # png/jpeg are not in our depends, so they are empty.
            setup_file = setup_template.format(
                sdl_includes=" ".join(sdl_libs),
                sdl_ttf_includes=sdl_ttf_includes,
                sdl_image_includes=sdl_image_includes,
                sdl_mixer_includes=sdl_mixer_includes,
                jpeg_includes="",
                png_includes="",
                freetype_includes=""
            )
            open("Setup", "w").write(setup_file)

    def get_recipe_env(self, arch):
        env = super().get_recipe_env(arch)
        env["USE_SDL2"] = "1"
        env["PYGAME_CROSS_COMPILE"] = "TRUE"
        env["PYGAME_ANDROID"] = "TRUE"
        return env


recipe = PygameCeRecipe()
