from conans import ConanFile, AutoToolsBuildEnvironment, tools
import os
import shutil


class GPGErrorConan(ConanFile):
    name = "libgpg-error"
    version = "1.36"
    homepage = "https://gnupg.org/software/libgpg-error/index.html"
    url = "http://github.com/bincrafters/conan-libgpg-error"
    topics = ("conan", "gpg", "gnupg")
    description = "Libgpg-error is a small library that originally defined common error values for all GnuPG " \
                  "components."
    license = "GPL-2.0-or-later"
    exports_sources = ["CMakeLists.txt"]
    settings = "os", "arch", "compiler", "build_type"
    options = {"shared": [True, False], "fPIC": [True, False]}
    default_options = {"shared": False, "fPIC": True}
    _source_subfolder = "sources"

    @property
    def _is_msvc(self):
        return self.settings.compiler == "Visual Studio"

    def build_requirements(self):
        if tools.os_info.is_windows:
            if "CONAN_BASH_PATH" not in os.environ:
                self.build_requires("cygwin_installer/2.9.0@bincrafters/stable")
        if self._is_msvc:
            self.build_requires("automake/1.16.1")

    def configure(self):
        del self.settings.compiler.libcxx
        del self.settings.compiler.cppstd

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC

    def source(self):
        source_url = "https://www.gnupg.org/ftp/gcrypt/libgpg-error"
        tools.get("{0}/libgpg-error-{1}.tar.bz2".format(source_url, self.version),
                  sha256="babd98437208c163175c29453f8681094bcaf92968a15cafb1a276076b33c97c")
        extracted_dir = self.name + "-" + self.version
        os.rename(extracted_dir, self._source_subfolder)

    def _apply_msvc_fixes(self):
        unistd_h = """
#ifdef _MSC_VER
#define access _access
#define R_OK 4
#define W_OK 2
#define X_OK R_OK
#define F_OK 0

# define S_IRWXU    0700
# define S_IRUSR    0400
# define S_IWUSR    0200
# define S_IXUSR    0100

typedef int ssize_t;
#else
#include <unistd.h>
#endif
"""
        os.makedirs(os.path.join(self._source_subfolder, "src", "sys"))
        tools.save(os.path.join(self._source_subfolder, "src", "unistd.h"), unistd_h)
        tools.save(os.path.join(self._source_subfolder, "src", "sys", "file.h"), unistd_h)
        tools.replace_in_file(os.path.join(self._source_subfolder, "src", "gpg-error.c"), '\x0c', '')
        tools.replace_in_file(os.path.join(self._source_subfolder, "src", "gpg-error.h.in"),
                              "#undef GPGRT_HAVE_MACRO_FUNCTION",
                              """#undef GPGRT_HAVE_MACRO_FUNCTION
#ifdef _MSC_VER
#define GPGRT_HAVE_MACRO_FUNCTION 1
#endif
""")
        tools.replace_in_file(os.path.join(self._source_subfolder, "src", "gpg-error.c"),
                              """#if HAVE_W32_SYSTEM
                "Return the locale used for gettext"
#else
                "@"
#endif""",
                              '                "Return the locale used for gettext"')
        tools.replace_in_file(os.path.join(self._source_subfolder, "src", "Makefile.in"),
                              "$(CPP) $(CPPFLAGS) $(extra_cppflags) -P _$@",
                              "$(CPP) $(CPPFLAGS) $(extra_cppflags) -EP _$@")
        tools.replace_in_file(os.path.join(self._source_subfolder, "src", "w32-estream.c"),
                              "#include <windows.h>", "#include <windows.h>\n" + unistd_h)

    def build(self):

        # the previous step might hang when converting from ISO-8859-2 to UTF-8 late in the build process
        os.unlink(os.path.join(self._source_subfolder, "po", "ro.po"))
        build = None
        host = None
        rc = None
        env = dict()
        args = ["--disable-dependency-tracking",
                "--disable-nls",
                "--disable-languages",
                "--disable-doc",
                "--disable-tests"]
        if self.settings.os != "Windows" and self.options.fPIC:
            args.append("--with-pic")
        if self.options.shared:
            args.extend(["--disable-static", "--enable-shared"])
        else:
            args.extend(["--disable-shared", "--enable-static"])
        if self.settings.os == "Linux" and self.settings.arch == "x86":
            host = "i686-linux-gnu"

        if self._is_msvc:
            env["_LINK_"] = "advapi32.lib"
            self._apply_msvc_fixes()
            # INSTALL.windows: Native binaries, built using the MS Visual C/C++ tool chain.
            build = False
            if self.settings.arch == "x86":
                host = "i686-w64-mingw32"
                rc = "windres --target=pe-i386"
            elif self.settings.arch == "x86_64":
                host = "x86_64-w64-mingw32"
                rc = "windres --target=pe-x86-64"
            automake_perldir = os.getenv('AUTOMAKE_PERLLIBDIR')
            if automake_perldir.startswith('/mnt/'):
                automake_perldir = automake_perldir[4:]
            args.extend(["CC=%s/compile cl -nologo" % automake_perldir,
                         "LD=link",
                         "NM=dumpbin -symbols",
                         "STRIP=:",
                         "AR=%s/ar-lib lib" % automake_perldir,
                         "RANLIB=:",
                         "gnupg_cv_mkdir_takes_one_arg=yes"])
            if rc:
                args.extend(['RC=%s' % rc, 'WINDRES=%s' % rc])

        with tools.chdir(self._source_subfolder):
            with tools.vcvars(self.settings) if self._is_msvc else tools.no_op():
                with tools.environment_append(env):
                    env_build = AutoToolsBuildEnvironment(self, win_bash=tools.os_info.is_windows)
                    if self._is_msvc:
                        env_build.defines.extend(["strncasecmp=_strnicmp", "strcasecmp=_stricmp"])
                        env_build.flags.append("-FS")
                    env_build.configure(args=args, build=build, host=host)
                    env_build.make()
                    env_build.install()

    def package(self):
        self.copy(pattern="COPYING", dst="licenses", src=self._source_subfolder)
        la = os.path.join(self.package_folder, "lib", "libgpg-error.la")
        if os.path.isfile(la):
            os.unlink(la)

    def package_info(self):
        self.cpp_info.libs = ["gpg-error"]
        if self.settings.os == "Windows":
            self.cpp_info.libs.append("ws2_32")
