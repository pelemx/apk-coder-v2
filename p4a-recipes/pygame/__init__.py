"""JuprisX pygame 2.6.1 Android recipe.

The stock python-for-android pygame recipe is still based on pygame 2.1.0.
This local recipe pins pygame 2.6.1 and installs the Cython version required
by pygame into *hostpython* before setup.py build_ext runs.

It also restores pygame 2.6.1's SIMD blitter sources to the Android surface
extension; otherwise a successful build can still produce a runtime
dlopen/undefined-symbol failure on ARM.
"""
from os.path import join

from pythonforandroid.recipe import CompiledComponentsPythonRecipe
from pythonforandroid.toolchain import current_directory


class JuprisXPygameRecipe(CompiledComponentsPythonRecipe):
    version = "2.6.1"
    url = "https://github.com/pygame/pygame/archive/{version}.tar.gz"

    site_packages_name = "pygame"
    name = "pygame"

    depends = [
        "sdl2", "sdl2_image", "sdl2_mixer", "sdl2_ttf",
        "setuptools", "jpeg", "png",
    ]
    call_hostpython_via_targetpython = False
    install_in_hostpython = False

    # pygame 2.6.1's build configuration pins Cython to the 3.0.x line.
    # Most importantly: this installs it into the hostpython used by
    # setup.py build_ext, not merely the outer Buildozer venv.
    hostpython_prerequisites = ["setuptools", "Cython==3.0.12"]

    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)
        with current_directory(self.get_build_dir(arch.arch)):
            setup_template = open(
                join("buildconfig", "Setup.Android.SDL2.in"),
                encoding="utf-8",
            ).read()

            env = self.get_recipe_env(arch)
            env["ANDROID_ROOT"] = join(self.ctx.ndk.sysroot, "usr")

            png = self.get_recipe("png", self.ctx)
            png_lib_dir = join(png.get_build_dir(arch.arch), ".libs")
            png_inc_dir = png.get_build_dir(arch)

            jpeg = self.get_recipe("jpeg", self.ctx)
            jpeg_inc_dir = jpeg_lib_dir = jpeg.get_build_dir(arch.arch)

            sdl_mixer_includes = ""
            sdl2_mixer_recipe = self.get_recipe("sdl2_mixer", self.ctx)
            for include_dir in sdl2_mixer_recipe.get_include_dirs(arch):
                sdl_mixer_includes += f"-I{include_dir} "

            sdl2_image_includes = ""
            sdl2_image_recipe = self.get_recipe("sdl2_image", self.ctx)
            for include_dir in sdl2_image_recipe.get_include_dirs(arch):
                sdl2_image_includes += f"-I{include_dir} "

            setup_file = setup_template.format(
                sdl_includes=(
                    " -I" + join(self.ctx.bootstrap.build_dir, "jni", "SDL", "include")
                    + " -L" + join(self.ctx.bootstrap.build_dir, "libs", str(arch))
                    + " -L" + png_lib_dir
                    + " -L" + jpeg_lib_dir
                    + " -L" + arch.ndk_lib_dir_versioned
                ),
                sdl_ttf_includes="-I" + join(
                    self.ctx.bootstrap.build_dir, "jni", "SDL2_ttf"
                ),
                sdl_image_includes=sdl2_image_includes,
                sdl_mixer_includes=sdl_mixer_includes,
                jpeg_includes="-I" + jpeg_inc_dir,
                png_includes="-I" + png_inc_dir,
                freetype_includes="",
            )

            # pygame 2.6.1 alphablit code references these ARM/portable
            # SIMD entry points. The upstream p4a template omits them.
            surface_old = (
                "surface src_c/surface.c src_c/alphablit.c "
                "$(SDL) $(DEBUG)"
            )
            surface_new = (
                "surface src_c/surface.c src_c/alphablit.c "
                "src_c/simd_blitters_sse2.c src_c/simd_blitters_avx2.c "
                "$(SDL) $(DEBUG)"
            )
            if surface_old in setup_file:
                setup_file = setup_file.replace(surface_old, surface_new)

            open("Setup", "w", encoding="utf-8").write(setup_file)

    def get_recipe_env(self, arch):
        env = super().get_recipe_env(arch)
        env["USE_SDL2"] = "1"
        env["PYGAME_CROSS_COMPILE"] = "TRUE"
        env["PYGAME_ANDROID"] = "TRUE"
        # Enable pygame's NEON-compatible path on ARM. The source itself
        # guards the implementation with PG_ENABLE_ARM_NEON.
        if arch.arch in ("arm64-v8a", "armeabi-v7a"):
            env["CFLAGS"] = env.get("CFLAGS", "") + " -DPG_ENABLE_ARM_NEON=1"
            env["CPPFLAGS"] = env.get("CPPFLAGS", "") + " -DPG_ENABLE_ARM_NEON=1"
        return env


recipe = JuprisXPygameRecipe()
