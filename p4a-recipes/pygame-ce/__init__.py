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
    requirements = python3==3.11.15,pygame-ce
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
            env = self.get_recipe_env(arch)
            ndk_sysroot = self.ctx.ndk.sysroot if hasattr(self.ctx, "ndk") and hasattr(self.ctx.ndk, "sysroot") else getattr(self.ctx, "ndk_sysroot", "")
            if ndk_sysroot:
                env["ANDROID_ROOT"] = join(ndk_sysroot, "usr")

            png_lib_dir = ""
            png_inc_dir = ""
            if self.ctx.has_recipe("png"):
                png = self.get_recipe("png", self.ctx)
                png_lib_dir = join(png.get_build_dir(arch.arch), ".libs")
                png_inc_dir = png.get_build_dir(arch.arch)

            jpeg_inc_dir = ""
            jpeg_lib_dir = ""
            if self.ctx.has_recipe("jpeg"):
                jpeg = self.get_recipe("jpeg", self.ctx)
                jpeg_inc_dir = jpeg_lib_dir = join(jpeg.get_build_dir(arch.arch))

            sdl_mixer_includes = ""
            if self.ctx.has_recipe("sdl2_mixer"):
                sdl2_mixer_recipe = self.get_recipe("sdl2_mixer", self.ctx)
                for include_dir in sdl2_mixer_recipe.get_include_dirs(arch):
                    sdl_mixer_includes += f"-I{include_dir} "

            sdl_image_includes = ""
            if self.ctx.has_recipe("sdl2_image"):
                sdl2_image_recipe = self.get_recipe("sdl2_image", self.ctx)
                for include_dir in sdl2_image_recipe.get_include_dirs(arch):
                    sdl_image_includes += f"-I{include_dir} "

            ndk_lib = getattr(arch, "ndk_lib_dir_versioned", getattr(arch, "ndk_lib_dir", ""))

            sdl_libs = [
                " -I" + join(self.ctx.bootstrap.build_dir, "jni", "SDL", "include"),
                " -L" + join(self.ctx.bootstrap.build_dir, "libs", str(arch))
            ]
            if png_lib_dir:
                sdl_libs.append(" -L" + png_lib_dir)
            if jpeg_lib_dir:
                sdl_libs.append(" -L" + jpeg_lib_dir)
            if ndk_lib:
                sdl_libs.append(" -L" + ndk_lib)

            setup_file = setup_template.format(
                sdl_includes="".join(sdl_libs),
                sdl_ttf_includes="-I" + join(
                    self.ctx.bootstrap.build_dir, "jni", "SDL2_ttf"),
                sdl_image_includes=sdl_image_includes,
                sdl_mixer_includes=sdl_mixer_includes,
                jpeg_includes=("-I" + jpeg_inc_dir) if jpeg_inc_dir else "",
                png_includes=("-I" + png_inc_dir) if png_inc_dir else "",
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
