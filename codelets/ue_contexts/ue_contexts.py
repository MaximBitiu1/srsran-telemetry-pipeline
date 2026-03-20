r"""Wrapper for ue_contexts.pb.h

Generated with:
/home/maxim/.local/bin/ctypesgen ue_contexts.pb.h -I/home/maxim/Desktop/jrtc-apps/jbpf_protobuf/3p/nanopb -o ue_contexts.py

Do not modify this file.
"""

__docformat__ = "restructuredtext"

# Begin preamble for Python

import ctypes
import sys
from ctypes import *  # noqa: F401, F403

_int_types = (ctypes.c_int16, ctypes.c_int32)
if hasattr(ctypes, "c_int64"):
    # Some builds of ctypes apparently do not have ctypes.c_int64
    # defined; it's a pretty good bet that these builds do not
    # have 64-bit pointers.
    _int_types += (ctypes.c_int64,)
for t in _int_types:
    if ctypes.sizeof(t) == ctypes.sizeof(ctypes.c_size_t):
        c_ptrdiff_t = t
del t
del _int_types



class UserString:
    def __init__(self, seq):
        if isinstance(seq, bytes):
            self.data = seq
        elif isinstance(seq, UserString):
            self.data = seq.data[:]
        else:
            self.data = str(seq).encode()

    def __bytes__(self):
        return self.data

    def __str__(self):
        return self.data.decode()

    def __repr__(self):
        return repr(self.data)

    def __int__(self):
        return int(self.data.decode())

    def __long__(self):
        return int(self.data.decode())

    def __float__(self):
        return float(self.data.decode())

    def __complex__(self):
        return complex(self.data.decode())

    def __hash__(self):
        return hash(self.data)

    def __le__(self, string):
        if isinstance(string, UserString):
            return self.data <= string.data
        else:
            return self.data <= string

    def __lt__(self, string):
        if isinstance(string, UserString):
            return self.data < string.data
        else:
            return self.data < string

    def __ge__(self, string):
        if isinstance(string, UserString):
            return self.data >= string.data
        else:
            return self.data >= string

    def __gt__(self, string):
        if isinstance(string, UserString):
            return self.data > string.data
        else:
            return self.data > string

    def __eq__(self, string):
        if isinstance(string, UserString):
            return self.data == string.data
        else:
            return self.data == string

    def __ne__(self, string):
        if isinstance(string, UserString):
            return self.data != string.data
        else:
            return self.data != string

    def __contains__(self, char):
        return char in self.data

    def __len__(self):
        return len(self.data)

    def __getitem__(self, index):
        return self.__class__(self.data[index])

    def __getslice__(self, start, end):
        start = max(start, 0)
        end = max(end, 0)
        return self.__class__(self.data[start:end])

    def __add__(self, other):
        if isinstance(other, UserString):
            return self.__class__(self.data + other.data)
        elif isinstance(other, bytes):
            return self.__class__(self.data + other)
        else:
            return self.__class__(self.data + str(other).encode())

    def __radd__(self, other):
        if isinstance(other, bytes):
            return self.__class__(other + self.data)
        else:
            return self.__class__(str(other).encode() + self.data)

    def __mul__(self, n):
        return self.__class__(self.data * n)

    __rmul__ = __mul__

    def __mod__(self, args):
        return self.__class__(self.data % args)

    # the following methods are defined in alphabetical order:
    def capitalize(self):
        return self.__class__(self.data.capitalize())

    def center(self, width, *args):
        return self.__class__(self.data.center(width, *args))

    def count(self, sub, start=0, end=sys.maxsize):
        return self.data.count(sub, start, end)

    def decode(self, encoding=None, errors=None):  # XXX improve this?
        if encoding:
            if errors:
                return self.__class__(self.data.decode(encoding, errors))
            else:
                return self.__class__(self.data.decode(encoding))
        else:
            return self.__class__(self.data.decode())

    def encode(self, encoding=None, errors=None):  # XXX improve this?
        if encoding:
            if errors:
                return self.__class__(self.data.encode(encoding, errors))
            else:
                return self.__class__(self.data.encode(encoding))
        else:
            return self.__class__(self.data.encode())

    def endswith(self, suffix, start=0, end=sys.maxsize):
        return self.data.endswith(suffix, start, end)

    def expandtabs(self, tabsize=8):
        return self.__class__(self.data.expandtabs(tabsize))

    def find(self, sub, start=0, end=sys.maxsize):
        return self.data.find(sub, start, end)

    def index(self, sub, start=0, end=sys.maxsize):
        return self.data.index(sub, start, end)

    def isalpha(self):
        return self.data.isalpha()

    def isalnum(self):
        return self.data.isalnum()

    def isdecimal(self):
        return self.data.isdecimal()

    def isdigit(self):
        return self.data.isdigit()

    def islower(self):
        return self.data.islower()

    def isnumeric(self):
        return self.data.isnumeric()

    def isspace(self):
        return self.data.isspace()

    def istitle(self):
        return self.data.istitle()

    def isupper(self):
        return self.data.isupper()

    def join(self, seq):
        return self.data.join(seq)

    def ljust(self, width, *args):
        return self.__class__(self.data.ljust(width, *args))

    def lower(self):
        return self.__class__(self.data.lower())

    def lstrip(self, chars=None):
        return self.__class__(self.data.lstrip(chars))

    def partition(self, sep):
        return self.data.partition(sep)

    def replace(self, old, new, maxsplit=-1):
        return self.__class__(self.data.replace(old, new, maxsplit))

    def rfind(self, sub, start=0, end=sys.maxsize):
        return self.data.rfind(sub, start, end)

    def rindex(self, sub, start=0, end=sys.maxsize):
        return self.data.rindex(sub, start, end)

    def rjust(self, width, *args):
        return self.__class__(self.data.rjust(width, *args))

    def rpartition(self, sep):
        return self.data.rpartition(sep)

    def rstrip(self, chars=None):
        return self.__class__(self.data.rstrip(chars))

    def split(self, sep=None, maxsplit=-1):
        return self.data.split(sep, maxsplit)

    def rsplit(self, sep=None, maxsplit=-1):
        return self.data.rsplit(sep, maxsplit)

    def splitlines(self, keepends=0):
        return self.data.splitlines(keepends)

    def startswith(self, prefix, start=0, end=sys.maxsize):
        return self.data.startswith(prefix, start, end)

    def strip(self, chars=None):
        return self.__class__(self.data.strip(chars))

    def swapcase(self):
        return self.__class__(self.data.swapcase())

    def title(self):
        return self.__class__(self.data.title())

    def translate(self, *args):
        return self.__class__(self.data.translate(*args))

    def upper(self):
        return self.__class__(self.data.upper())

    def zfill(self, width):
        return self.__class__(self.data.zfill(width))


class MutableString(UserString):
    """mutable string objects

    Python strings are immutable objects.  This has the advantage, that
    strings may be used as dictionary keys.  If this property isn't needed
    and you insist on changing string values in place instead, you may cheat
    and use MutableString.

    But the purpose of this class is an educational one: to prevent
    people from inventing their own mutable string class derived
    from UserString and than forget thereby to remove (override) the
    __hash__ method inherited from UserString.  This would lead to
    errors that would be very hard to track down.

    A faster and better solution is to rewrite your program using lists."""

    def __init__(self, string=""):
        self.data = string

    def __hash__(self):
        raise TypeError("unhashable type (it is mutable)")

    def __setitem__(self, index, sub):
        if index < 0:
            index += len(self.data)
        if index < 0 or index >= len(self.data):
            raise IndexError
        self.data = self.data[:index] + sub + self.data[index + 1 :]

    def __delitem__(self, index):
        if index < 0:
            index += len(self.data)
        if index < 0 or index >= len(self.data):
            raise IndexError
        self.data = self.data[:index] + self.data[index + 1 :]

    def __setslice__(self, start, end, sub):
        start = max(start, 0)
        end = max(end, 0)
        if isinstance(sub, UserString):
            self.data = self.data[:start] + sub.data + self.data[end:]
        elif isinstance(sub, bytes):
            self.data = self.data[:start] + sub + self.data[end:]
        else:
            self.data = self.data[:start] + str(sub).encode() + self.data[end:]

    def __delslice__(self, start, end):
        start = max(start, 0)
        end = max(end, 0)
        self.data = self.data[:start] + self.data[end:]

    def immutable(self):
        return UserString(self.data)

    def __iadd__(self, other):
        if isinstance(other, UserString):
            self.data += other.data
        elif isinstance(other, bytes):
            self.data += other
        else:
            self.data += str(other).encode()
        return self

    def __imul__(self, n):
        self.data *= n
        return self


class String(MutableString, ctypes.Union):

    _fields_ = [("raw", ctypes.POINTER(ctypes.c_char)), ("data", ctypes.c_char_p)]

    def __init__(self, obj=b""):
        if isinstance(obj, (bytes, UserString)):
            self.data = bytes(obj)
        else:
            self.raw = obj

    def __len__(self):
        return self.data and len(self.data) or 0

    def from_param(cls, obj):
        # Convert None or 0
        if obj is None or obj == 0:
            return cls(ctypes.POINTER(ctypes.c_char)())

        # Convert from String
        elif isinstance(obj, String):
            return obj

        # Convert from bytes
        elif isinstance(obj, bytes):
            return cls(obj)

        # Convert from str
        elif isinstance(obj, str):
            return cls(obj.encode())

        # Convert from c_char_p
        elif isinstance(obj, ctypes.c_char_p):
            return obj

        # Convert from POINTER(ctypes.c_char)
        elif isinstance(obj, ctypes.POINTER(ctypes.c_char)):
            return obj

        # Convert from raw pointer
        elif isinstance(obj, int):
            return cls(ctypes.cast(obj, ctypes.POINTER(ctypes.c_char)))

        # Convert from ctypes.c_char array
        elif isinstance(obj, ctypes.c_char * len(obj)):
            return obj

        # Convert from object
        else:
            return String.from_param(obj._as_parameter_)

    from_param = classmethod(from_param)


def ReturnString(obj, func=None, arguments=None):
    return String.from_param(obj)


# As of ctypes 1.0, ctypes does not support custom error-checking
# functions on callbacks, nor does it support custom datatypes on
# callbacks, so we must ensure that all callbacks return
# primitive datatypes.
#
# Non-primitive return values wrapped with UNCHECKED won't be
# typechecked, and will be converted to ctypes.c_void_p.
def UNCHECKED(type):
    if hasattr(type, "_type_") and isinstance(type._type_, str) and type._type_ != "P":
        return type
    else:
        return ctypes.c_void_p


# ctypes doesn't have direct support for variadic functions, so we have to write
# our own wrapper class
class _variadic_function(object):
    def __init__(self, func, restype, argtypes, errcheck):
        self.func = func
        self.func.restype = restype
        self.argtypes = argtypes
        if errcheck:
            self.func.errcheck = errcheck

    def _as_parameter_(self):
        # So we can pass this variadic function as a function pointer
        return self.func

    def __call__(self, *args):
        fixed_args = []
        i = 0
        for argtype in self.argtypes:
            # Typecheck what we can
            fixed_args.append(argtype.from_param(args[i]))
            i += 1
        return self.func(*fixed_args + list(args[i:]))


def ord_if_char(value):
    """
    Simple helper used for casts to simple builtin types:  if the argument is a
    string type, it will be converted to it's ordinal value.

    This function will raise an exception if the argument is string with more
    than one characters.
    """
    return ord(value) if (isinstance(value, bytes) or isinstance(value, str)) else value

# End preamble

_libs = {}
_libdirs = []

# Begin loader

"""
Load libraries - appropriately for all our supported platforms
"""
# ----------------------------------------------------------------------------
# Copyright (c) 2008 David James
# Copyright (c) 2006-2008 Alex Holkner
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in
#    the documentation and/or other materials provided with the
#    distribution.
#  * Neither the name of pyglet nor the names of its
#    contributors may be used to endorse or promote products
#    derived from this software without specific prior written
#    permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
# ----------------------------------------------------------------------------

import ctypes
import ctypes.util
import glob
import os.path
import platform
import re
import sys


def _environ_path(name):
    """Split an environment variable into a path-like list elements"""
    if name in os.environ:
        return os.environ[name].split(":")
    return []


class LibraryLoader:
    """
    A base class For loading of libraries ;-)
    Subclasses load libraries for specific platforms.
    """

    # library names formatted specifically for platforms
    name_formats = ["%s"]

    class Lookup:
        """Looking up calling conventions for a platform"""

        mode = ctypes.DEFAULT_MODE

        def __init__(self, path):
            super(LibraryLoader.Lookup, self).__init__()
            self.access = dict(cdecl=ctypes.CDLL(path, self.mode))

        def get(self, name, calling_convention="cdecl"):
            """Return the given name according to the selected calling convention"""
            if calling_convention not in self.access:
                raise LookupError(
                    "Unknown calling convention '{}' for function '{}'".format(
                        calling_convention, name
                    )
                )
            return getattr(self.access[calling_convention], name)

        def has(self, name, calling_convention="cdecl"):
            """Return True if this given calling convention finds the given 'name'"""
            if calling_convention not in self.access:
                return False
            return hasattr(self.access[calling_convention], name)

        def __getattr__(self, name):
            return getattr(self.access["cdecl"], name)

    def __init__(self):
        self.other_dirs = []

    def __call__(self, libname):
        """Given the name of a library, load it."""
        paths = self.getpaths(libname)

        for path in paths:
            # noinspection PyBroadException
            try:
                return self.Lookup(path)
            except Exception:  # pylint: disable=broad-except
                pass

        raise ImportError("Could not load %s." % libname)

    def getpaths(self, libname):
        """Return a list of paths where the library might be found."""
        if os.path.isabs(libname):
            yield libname
        else:
            # search through a prioritized series of locations for the library

            # we first search any specific directories identified by user
            for dir_i in self.other_dirs:
                for fmt in self.name_formats:
                    # dir_i should be absolute already
                    yield os.path.join(dir_i, fmt % libname)

            # check if this code is even stored in a physical file
            try:
                this_file = __file__
            except NameError:
                this_file = None

            # then we search the directory where the generated python interface is stored
            if this_file is not None:
                for fmt in self.name_formats:
                    yield os.path.abspath(os.path.join(os.path.dirname(__file__), fmt % libname))

            # now, use the ctypes tools to try to find the library
            for fmt in self.name_formats:
                path = ctypes.util.find_library(fmt % libname)
                if path:
                    yield path

            # then we search all paths identified as platform-specific lib paths
            for path in self.getplatformpaths(libname):
                yield path

            # Finally, we'll try the users current working directory
            for fmt in self.name_formats:
                yield os.path.abspath(os.path.join(os.path.curdir, fmt % libname))

    def getplatformpaths(self, _libname):  # pylint: disable=no-self-use
        """Return all the library paths available in this platform"""
        return []


# Darwin (Mac OS X)


class DarwinLibraryLoader(LibraryLoader):
    """Library loader for MacOS"""

    name_formats = [
        "lib%s.dylib",
        "lib%s.so",
        "lib%s.bundle",
        "%s.dylib",
        "%s.so",
        "%s.bundle",
        "%s",
    ]

    class Lookup(LibraryLoader.Lookup):
        """
        Looking up library files for this platform (Darwin aka MacOS)
        """

        # Darwin requires dlopen to be called with mode RTLD_GLOBAL instead
        # of the default RTLD_LOCAL.  Without this, you end up with
        # libraries not being loadable, resulting in "Symbol not found"
        # errors
        mode = ctypes.RTLD_GLOBAL

    def getplatformpaths(self, libname):
        if os.path.pathsep in libname:
            names = [libname]
        else:
            names = [fmt % libname for fmt in self.name_formats]

        for directory in self.getdirs(libname):
            for name in names:
                yield os.path.join(directory, name)

    @staticmethod
    def getdirs(libname):
        """Implements the dylib search as specified in Apple documentation:

        http://developer.apple.com/documentation/DeveloperTools/Conceptual/
            DynamicLibraries/Articles/DynamicLibraryUsageGuidelines.html

        Before commencing the standard search, the method first checks
        the bundle's ``Frameworks`` directory if the application is running
        within a bundle (OS X .app).
        """

        dyld_fallback_library_path = _environ_path("DYLD_FALLBACK_LIBRARY_PATH")
        if not dyld_fallback_library_path:
            dyld_fallback_library_path = [
                os.path.expanduser("~/lib"),
                "/usr/local/lib",
                "/usr/lib",
            ]

        dirs = []

        if "/" in libname:
            dirs.extend(_environ_path("DYLD_LIBRARY_PATH"))
        else:
            dirs.extend(_environ_path("LD_LIBRARY_PATH"))
            dirs.extend(_environ_path("DYLD_LIBRARY_PATH"))
            dirs.extend(_environ_path("LD_RUN_PATH"))

        if hasattr(sys, "frozen") and getattr(sys, "frozen") == "macosx_app":
            dirs.append(os.path.join(os.environ["RESOURCEPATH"], "..", "Frameworks"))

        dirs.extend(dyld_fallback_library_path)

        return dirs


# Posix


class PosixLibraryLoader(LibraryLoader):
    """Library loader for POSIX-like systems (including Linux)"""

    _ld_so_cache = None

    _include = re.compile(r"^\s*include\s+(?P<pattern>.*)")

    name_formats = ["lib%s.so", "%s.so", "%s"]

    class _Directories(dict):
        """Deal with directories"""

        def __init__(self):
            dict.__init__(self)
            self.order = 0

        def add(self, directory):
            """Add a directory to our current set of directories"""
            if len(directory) > 1:
                directory = directory.rstrip(os.path.sep)
            # only adds and updates order if exists and not already in set
            if not os.path.exists(directory):
                return
            order = self.setdefault(directory, self.order)
            if order == self.order:
                self.order += 1

        def extend(self, directories):
            """Add a list of directories to our set"""
            for a_dir in directories:
                self.add(a_dir)

        def ordered(self):
            """Sort the list of directories"""
            return (i[0] for i in sorted(self.items(), key=lambda d: d[1]))

    def _get_ld_so_conf_dirs(self, conf, dirs):
        """
        Recursive function to help parse all ld.so.conf files, including proper
        handling of the `include` directive.
        """

        try:
            with open(conf) as fileobj:
                for dirname in fileobj:
                    dirname = dirname.strip()
                    if not dirname:
                        continue

                    match = self._include.match(dirname)
                    if not match:
                        dirs.add(dirname)
                    else:
                        for dir2 in glob.glob(match.group("pattern")):
                            self._get_ld_so_conf_dirs(dir2, dirs)
        except IOError:
            pass

    def _create_ld_so_cache(self):
        # Recreate search path followed by ld.so.  This is going to be
        # slow to build, and incorrect (ld.so uses ld.so.cache, which may
        # not be up-to-date).  Used only as fallback for distros without
        # /sbin/ldconfig.
        #
        # We assume the DT_RPATH and DT_RUNPATH binary sections are omitted.

        directories = self._Directories()
        for name in (
            "LD_LIBRARY_PATH",
            "SHLIB_PATH",  # HP-UX
            "LIBPATH",  # OS/2, AIX
            "LIBRARY_PATH",  # BE/OS
        ):
            if name in os.environ:
                directories.extend(os.environ[name].split(os.pathsep))

        self._get_ld_so_conf_dirs("/etc/ld.so.conf", directories)

        bitage = platform.architecture()[0]

        unix_lib_dirs_list = []
        if bitage.startswith("64"):
            # prefer 64 bit if that is our arch
            unix_lib_dirs_list += ["/lib64", "/usr/lib64"]

        # must include standard libs, since those paths are also used by 64 bit
        # installs
        unix_lib_dirs_list += ["/lib", "/usr/lib"]
        if sys.platform.startswith("linux"):
            # Try and support multiarch work in Ubuntu
            # https://wiki.ubuntu.com/MultiarchSpec
            if bitage.startswith("32"):
                # Assume Intel/AMD x86 compat
                unix_lib_dirs_list += ["/lib/i386-linux-gnu", "/usr/lib/i386-linux-gnu"]
            elif bitage.startswith("64"):
                # Assume Intel/AMD x86 compatible
                unix_lib_dirs_list += [
                    "/lib/x86_64-linux-gnu",
                    "/usr/lib/x86_64-linux-gnu",
                ]
            else:
                # guess...
                unix_lib_dirs_list += glob.glob("/lib/*linux-gnu")
        directories.extend(unix_lib_dirs_list)

        cache = {}
        lib_re = re.compile(r"lib(.*)\.s[ol]")
        # ext_re = re.compile(r"\.s[ol]$")
        for our_dir in directories.ordered():
            try:
                for path in glob.glob("%s/*.s[ol]*" % our_dir):
                    file = os.path.basename(path)

                    # Index by filename
                    cache_i = cache.setdefault(file, set())
                    cache_i.add(path)

                    # Index by library name
                    match = lib_re.match(file)
                    if match:
                        library = match.group(1)
                        cache_i = cache.setdefault(library, set())
                        cache_i.add(path)
            except OSError:
                pass

        self._ld_so_cache = cache

    def getplatformpaths(self, libname):
        if self._ld_so_cache is None:
            self._create_ld_so_cache()

        result = self._ld_so_cache.get(libname, set())
        for i in result:
            # we iterate through all found paths for library, since we may have
            # actually found multiple architectures or other library types that
            # may not load
            yield i


# Windows


class WindowsLibraryLoader(LibraryLoader):
    """Library loader for Microsoft Windows"""

    name_formats = ["%s.dll", "lib%s.dll", "%slib.dll", "%s"]

    class Lookup(LibraryLoader.Lookup):
        """Lookup class for Windows libraries..."""

        def __init__(self, path):
            super(WindowsLibraryLoader.Lookup, self).__init__(path)
            self.access["stdcall"] = ctypes.windll.LoadLibrary(path)


# Platform switching

# If your value of sys.platform does not appear in this dict, please contact
# the Ctypesgen maintainers.

loaderclass = {
    "darwin": DarwinLibraryLoader,
    "cygwin": WindowsLibraryLoader,
    "win32": WindowsLibraryLoader,
    "msys": WindowsLibraryLoader,
}

load_library = loaderclass.get(sys.platform, PosixLibraryLoader)()


def add_library_search_dirs(other_dirs):
    """
    Add libraries to search paths.
    If library paths are relative, convert them to absolute with respect to this
    file's directory
    """
    for path in other_dirs:
        if not os.path.isabs(path):
            path = os.path.abspath(path)
        load_library.other_dirs.append(path)


del loaderclass

# End loader

add_library_search_dirs([])

# No libraries

# No modules

__uint8_t = c_ubyte# /usr/include/x86_64-linux-gnu/bits/types.h: 38

__uint16_t = c_ushort# /usr/include/x86_64-linux-gnu/bits/types.h: 40

__uint32_t = c_uint# /usr/include/x86_64-linux-gnu/bits/types.h: 42

__uint64_t = c_ulong# /usr/include/x86_64-linux-gnu/bits/types.h: 45

__uint_least16_t = __uint16_t# /usr/include/x86_64-linux-gnu/bits/types.h: 55

uint8_t = __uint8_t# /usr/include/x86_64-linux-gnu/bits/stdint-uintn.h: 24

uint32_t = __uint32_t# /usr/include/x86_64-linux-gnu/bits/stdint-uintn.h: 26

uint64_t = __uint64_t# /usr/include/x86_64-linux-gnu/bits/stdint-uintn.h: 27

uint_least16_t = __uint_least16_t# /usr/include/stdint.h: 50

pb_byte_t = uint8_t# /home/maxim/Desktop/jrtc-apps/jbpf_protobuf/3p/nanopb/pb.h: 241

pb_type_t = pb_byte_t# /home/maxim/Desktop/jrtc-apps/jbpf_protobuf/3p/nanopb/pb.h: 250

pb_size_t = uint_least16_t# /home/maxim/Desktop/jrtc-apps/jbpf_protobuf/3p/nanopb/pb.h: 326

# /home/maxim/Desktop/jrtc-apps/jbpf_protobuf/3p/nanopb/pb.h: 332
class struct_pb_istream_s(Structure):
    pass

pb_istream_t = struct_pb_istream_s# /home/maxim/Desktop/jrtc-apps/jbpf_protobuf/3p/nanopb/pb.h: 332

# /home/maxim/Desktop/jrtc-apps/jbpf_protobuf/3p/nanopb/pb.h: 333
class struct_pb_ostream_s(Structure):
    pass

pb_ostream_t = struct_pb_ostream_s# /home/maxim/Desktop/jrtc-apps/jbpf_protobuf/3p/nanopb/pb.h: 333

# /home/maxim/Desktop/jrtc-apps/jbpf_protobuf/3p/nanopb/pb.h: 353
class struct_pb_field_iter_s(Structure):
    pass

pb_field_iter_t = struct_pb_field_iter_s# /home/maxim/Desktop/jrtc-apps/jbpf_protobuf/3p/nanopb/pb.h: 334

# /home/maxim/Desktop/jrtc-apps/jbpf_protobuf/3p/nanopb/pb.h: 340
class struct_pb_msgdesc_s(Structure):
    pass

pb_msgdesc_t = struct_pb_msgdesc_s# /home/maxim/Desktop/jrtc-apps/jbpf_protobuf/3p/nanopb/pb.h: 339

struct_pb_msgdesc_s.__slots__ = [
    'field_info',
    'submsg_info',
    'default_value',
    'field_callback',
    'field_count',
    'required_field_count',
    'largest_tag',
]
struct_pb_msgdesc_s._fields_ = [
    ('field_info', POINTER(uint32_t)),
    ('submsg_info', POINTER(POINTER(pb_msgdesc_t))),
    ('default_value', POINTER(pb_byte_t)),
    ('field_callback', CFUNCTYPE(UNCHECKED(c_bool), POINTER(pb_istream_t), POINTER(pb_ostream_t), POINTER(pb_field_iter_t))),
    ('field_count', pb_size_t),
    ('required_field_count', pb_size_t),
    ('largest_tag', pb_size_t),
]

struct_pb_field_iter_s.__slots__ = [
    'descriptor',
    'message',
    'index',
    'field_info_index',
    'required_field_index',
    'submessage_index',
    'tag',
    'data_size',
    'array_size',
    'type',
    'pField',
    'pData',
    'pSize',
    'submsg_desc',
]
struct_pb_field_iter_s._fields_ = [
    ('descriptor', POINTER(pb_msgdesc_t)),
    ('message', POINTER(None)),
    ('index', pb_size_t),
    ('field_info_index', pb_size_t),
    ('required_field_index', pb_size_t),
    ('submessage_index', pb_size_t),
    ('tag', pb_size_t),
    ('data_size', pb_size_t),
    ('array_size', pb_size_t),
    ('type', pb_type_t),
    ('pField', POINTER(None)),
    ('pData', POINTER(None)),
    ('pSize', POINTER(None)),
    ('submsg_desc', POINTER(pb_msgdesc_t)),
]

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 21
class struct__du_ue_ctx_creation(Structure):
    pass

struct__du_ue_ctx_creation.__slots__ = [
    'timestamp',
    'du_ue_index',
    'tac',
    'plmn',
    'nci',
    'pci',
    'crnti',
]
struct__du_ue_ctx_creation._fields_ = [
    ('timestamp', uint64_t),
    ('du_ue_index', uint32_t),
    ('tac', uint32_t),
    ('plmn', uint32_t),
    ('nci', uint32_t),
    ('pci', uint32_t),
    ('crnti', uint32_t),
]

du_ue_ctx_creation = struct__du_ue_ctx_creation# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 21

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 27
class struct__du_ue_ctx_update_crnti(Structure):
    pass

struct__du_ue_ctx_update_crnti.__slots__ = [
    'timestamp',
    'du_ue_index',
    'crnti',
]
struct__du_ue_ctx_update_crnti._fields_ = [
    ('timestamp', uint64_t),
    ('du_ue_index', uint32_t),
    ('crnti', uint32_t),
]

du_ue_ctx_update_crnti = struct__du_ue_ctx_update_crnti# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 27

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 32
class struct__du_ue_ctx_deletion(Structure):
    pass

struct__du_ue_ctx_deletion.__slots__ = [
    'timestamp',
    'du_ue_index',
]
struct__du_ue_ctx_deletion._fields_ = [
    ('timestamp', uint64_t),
    ('du_ue_index', uint32_t),
]

du_ue_ctx_deletion = struct__du_ue_ctx_deletion# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 32

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 42
class struct__cucp_ue_ctx_creation(Structure):
    pass

struct__cucp_ue_ctx_creation.__slots__ = [
    'timestamp',
    'cucp_ue_index',
    'plmn',
    'has_pci',
    'pci',
    'has_crnti',
    'crnti',
]
struct__cucp_ue_ctx_creation._fields_ = [
    ('timestamp', uint64_t),
    ('cucp_ue_index', uint32_t),
    ('plmn', uint32_t),
    ('has_pci', c_bool),
    ('pci', uint32_t),
    ('has_crnti', c_bool),
    ('crnti', uint32_t),
]

cucp_ue_ctx_creation = struct__cucp_ue_ctx_creation# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 42

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 50
class struct__cucp_ue_ctx_update(Structure):
    pass

struct__cucp_ue_ctx_update.__slots__ = [
    'timestamp',
    'cucp_ue_index',
    'plmn',
    'pci',
    'crnti',
]
struct__cucp_ue_ctx_update._fields_ = [
    ('timestamp', uint64_t),
    ('cucp_ue_index', uint32_t),
    ('plmn', uint32_t),
    ('pci', uint32_t),
    ('crnti', uint32_t),
]

cucp_ue_ctx_update = struct__cucp_ue_ctx_update# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 50

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 55
class struct__cucp_ue_ctx_deletion(Structure):
    pass

struct__cucp_ue_ctx_deletion.__slots__ = [
    'timestamp',
    'cucp_ue_index',
]
struct__cucp_ue_ctx_deletion._fields_ = [
    ('timestamp', uint64_t),
    ('cucp_ue_index', uint32_t),
]

cucp_ue_ctx_deletion = struct__cucp_ue_ctx_deletion# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 55

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 61
class struct__e1ap_cucp_bearer_ctx_setup(Structure):
    pass

struct__e1ap_cucp_bearer_ctx_setup.__slots__ = [
    'timestamp',
    'cucp_ue_index',
    'cucp_ue_e1ap_id',
]
struct__e1ap_cucp_bearer_ctx_setup._fields_ = [
    ('timestamp', uint64_t),
    ('cucp_ue_index', uint32_t),
    ('cucp_ue_e1ap_id', uint32_t),
]

e1ap_cucp_bearer_ctx_setup = struct__e1ap_cucp_bearer_ctx_setup# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 61

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 69
class struct__e1ap_cuup_bearer_ctx_setup(Structure):
    pass

struct__e1ap_cuup_bearer_ctx_setup.__slots__ = [
    'timestamp',
    'cuup_ue_index',
    'success',
    'cucp_ue_e1ap_id',
    'cuup_ue_e1ap_id',
]
struct__e1ap_cuup_bearer_ctx_setup._fields_ = [
    ('timestamp', uint64_t),
    ('cuup_ue_index', uint32_t),
    ('success', c_bool),
    ('cucp_ue_e1ap_id', uint32_t),
    ('cuup_ue_e1ap_id', uint32_t),
]

e1ap_cuup_bearer_ctx_setup = struct__e1ap_cuup_bearer_ctx_setup# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 69

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 77
class struct__e1ap_cuup_bearer_ctx_release(Structure):
    pass

struct__e1ap_cuup_bearer_ctx_release.__slots__ = [
    'timestamp',
    'cuup_ue_index',
    'success',
    'cucp_ue_e1ap_id',
    'cuup_ue_e1ap_id',
]
struct__e1ap_cuup_bearer_ctx_release._fields_ = [
    ('timestamp', uint64_t),
    ('cuup_ue_index', uint32_t),
    ('success', c_bool),
    ('cucp_ue_e1ap_id', uint32_t),
    ('cuup_ue_e1ap_id', uint32_t),
]

e1ap_cuup_bearer_ctx_release = struct__e1ap_cuup_bearer_ctx_release# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 77

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 82
class struct__nssai_t(Structure):
    pass

struct__nssai_t.__slots__ = [
    'sst',
    'sd',
]
struct__nssai_t._fields_ = [
    ('sst', uint32_t),
    ('sd', uint32_t),
]

nssai_t = struct__nssai_t# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 82

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 90
class struct__cucp_pdu_session_bearer_add_modify(Structure):
    pass

struct__cucp_pdu_session_bearer_add_modify.__slots__ = [
    'timestamp',
    'cucp_ue_index',
    'pdu_session_id',
    'drb_id',
    'nssai',
]
struct__cucp_pdu_session_bearer_add_modify._fields_ = [
    ('timestamp', uint64_t),
    ('cucp_ue_index', uint64_t),
    ('pdu_session_id', uint32_t),
    ('drb_id', uint32_t),
    ('nssai', nssai_t),
]

cucp_pdu_session_bearer_add_modify = struct__cucp_pdu_session_bearer_add_modify# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 90

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 96
class struct__cucp_pdu_session_remove(Structure):
    pass

struct__cucp_pdu_session_remove.__slots__ = [
    'timestamp',
    'cucp_ue_index',
    'pdu_session_id',
]
struct__cucp_pdu_session_remove._fields_ = [
    ('timestamp', uint64_t),
    ('cucp_ue_index', uint64_t),
    ('pdu_session_id', uint32_t),
]

cucp_pdu_session_remove = struct__cucp_pdu_session_remove# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 96

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 275
for _lib in _libs.values():
    try:
        du_ue_ctx_creation_msg = (pb_msgdesc_t).in_dll(_lib, "du_ue_ctx_creation_msg")
        break
    except:
        pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 276
for _lib in _libs.values():
    try:
        du_ue_ctx_update_crnti_msg = (pb_msgdesc_t).in_dll(_lib, "du_ue_ctx_update_crnti_msg")
        break
    except:
        pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 277
for _lib in _libs.values():
    try:
        du_ue_ctx_deletion_msg = (pb_msgdesc_t).in_dll(_lib, "du_ue_ctx_deletion_msg")
        break
    except:
        pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 278
for _lib in _libs.values():
    try:
        cucp_ue_ctx_creation_msg = (pb_msgdesc_t).in_dll(_lib, "cucp_ue_ctx_creation_msg")
        break
    except:
        pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 279
for _lib in _libs.values():
    try:
        cucp_ue_ctx_update_msg = (pb_msgdesc_t).in_dll(_lib, "cucp_ue_ctx_update_msg")
        break
    except:
        pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 280
for _lib in _libs.values():
    try:
        cucp_ue_ctx_deletion_msg = (pb_msgdesc_t).in_dll(_lib, "cucp_ue_ctx_deletion_msg")
        break
    except:
        pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 281
for _lib in _libs.values():
    try:
        e1ap_cucp_bearer_ctx_setup_msg = (pb_msgdesc_t).in_dll(_lib, "e1ap_cucp_bearer_ctx_setup_msg")
        break
    except:
        pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 282
for _lib in _libs.values():
    try:
        e1ap_cuup_bearer_ctx_setup_msg = (pb_msgdesc_t).in_dll(_lib, "e1ap_cuup_bearer_ctx_setup_msg")
        break
    except:
        pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 283
for _lib in _libs.values():
    try:
        e1ap_cuup_bearer_ctx_release_msg = (pb_msgdesc_t).in_dll(_lib, "e1ap_cuup_bearer_ctx_release_msg")
        break
    except:
        pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 284
for _lib in _libs.values():
    try:
        nssai_t_msg = (pb_msgdesc_t).in_dll(_lib, "nssai_t_msg")
        break
    except:
        pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 285
for _lib in _libs.values():
    try:
        cucp_pdu_session_bearer_add_modify_msg = (pb_msgdesc_t).in_dll(_lib, "cucp_pdu_session_bearer_add_modify_msg")
        break
    except:
        pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 286
for _lib in _libs.values():
    try:
        cucp_pdu_session_remove_msg = (pb_msgdesc_t).in_dll(_lib, "cucp_pdu_session_remove_msg")
        break
    except:
        pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 130
try:
    du_ue_ctx_creation_timestamp_tag = 1
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 131
try:
    du_ue_ctx_creation_du_ue_index_tag = 2
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 132
try:
    du_ue_ctx_creation_tac_tag = 3
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 133
try:
    du_ue_ctx_creation_plmn_tag = 4
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 134
try:
    du_ue_ctx_creation_nci_tag = 5
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 135
try:
    du_ue_ctx_creation_pci_tag = 6
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 136
try:
    du_ue_ctx_creation_crnti_tag = 7
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 137
try:
    du_ue_ctx_update_crnti_timestamp_tag = 1
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 138
try:
    du_ue_ctx_update_crnti_du_ue_index_tag = 2
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 139
try:
    du_ue_ctx_update_crnti_crnti_tag = 7
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 140
try:
    du_ue_ctx_deletion_timestamp_tag = 1
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 141
try:
    du_ue_ctx_deletion_du_ue_index_tag = 2
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 142
try:
    cucp_ue_ctx_creation_timestamp_tag = 1
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 143
try:
    cucp_ue_ctx_creation_cucp_ue_index_tag = 2
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 144
try:
    cucp_ue_ctx_creation_plmn_tag = 3
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 145
try:
    cucp_ue_ctx_creation_pci_tag = 4
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 146
try:
    cucp_ue_ctx_creation_crnti_tag = 5
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 147
try:
    cucp_ue_ctx_update_timestamp_tag = 1
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 148
try:
    cucp_ue_ctx_update_cucp_ue_index_tag = 2
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 149
try:
    cucp_ue_ctx_update_plmn_tag = 3
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 150
try:
    cucp_ue_ctx_update_pci_tag = 4
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 151
try:
    cucp_ue_ctx_update_crnti_tag = 5
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 152
try:
    cucp_ue_ctx_deletion_timestamp_tag = 1
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 153
try:
    cucp_ue_ctx_deletion_cucp_ue_index_tag = 2
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 154
try:
    e1ap_cucp_bearer_ctx_setup_timestamp_tag = 1
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 155
try:
    e1ap_cucp_bearer_ctx_setup_cucp_ue_index_tag = 2
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 156
try:
    e1ap_cucp_bearer_ctx_setup_cucp_ue_e1ap_id_tag = 3
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 157
try:
    e1ap_cuup_bearer_ctx_setup_timestamp_tag = 1
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 158
try:
    e1ap_cuup_bearer_ctx_setup_cuup_ue_index_tag = 2
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 159
try:
    e1ap_cuup_bearer_ctx_setup_success_tag = 3
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 160
try:
    e1ap_cuup_bearer_ctx_setup_cucp_ue_e1ap_id_tag = 4
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 161
try:
    e1ap_cuup_bearer_ctx_setup_cuup_ue_e1ap_id_tag = 5
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 162
try:
    e1ap_cuup_bearer_ctx_release_timestamp_tag = 1
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 163
try:
    e1ap_cuup_bearer_ctx_release_cuup_ue_index_tag = 2
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 164
try:
    e1ap_cuup_bearer_ctx_release_success_tag = 3
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 165
try:
    e1ap_cuup_bearer_ctx_release_cucp_ue_e1ap_id_tag = 4
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 166
try:
    e1ap_cuup_bearer_ctx_release_cuup_ue_e1ap_id_tag = 5
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 167
try:
    nssai_t_sst_tag = 1
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 168
try:
    nssai_t_sd_tag = 2
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 169
try:
    cucp_pdu_session_bearer_add_modify_timestamp_tag = 1
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 170
try:
    cucp_pdu_session_bearer_add_modify_cucp_ue_index_tag = 2
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 171
try:
    cucp_pdu_session_bearer_add_modify_pdu_session_id_tag = 3
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 172
try:
    cucp_pdu_session_bearer_add_modify_drb_id_tag = 4
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 173
try:
    cucp_pdu_session_bearer_add_modify_nssai_tag = 5
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 174
try:
    cucp_pdu_session_remove_timestamp_tag = 1
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 175
try:
    cucp_pdu_session_remove_cucp_ue_index_tag = 2
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 176
try:
    cucp_pdu_session_remove_pdu_session_id_tag = 3
except:
    pass

cucp_pdu_session_bearer_add_modify_nssai_MSGTYPE = nssai_t# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 266

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 289
try:
    du_ue_ctx_creation_fields = pointer(du_ue_ctx_creation_msg)
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 290
try:
    du_ue_ctx_update_crnti_fields = pointer(du_ue_ctx_update_crnti_msg)
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 291
try:
    du_ue_ctx_deletion_fields = pointer(du_ue_ctx_deletion_msg)
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 292
try:
    cucp_ue_ctx_creation_fields = pointer(cucp_ue_ctx_creation_msg)
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 293
try:
    cucp_ue_ctx_update_fields = pointer(cucp_ue_ctx_update_msg)
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 294
try:
    cucp_ue_ctx_deletion_fields = pointer(cucp_ue_ctx_deletion_msg)
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 295
try:
    e1ap_cucp_bearer_ctx_setup_fields = pointer(e1ap_cucp_bearer_ctx_setup_msg)
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 296
try:
    e1ap_cuup_bearer_ctx_setup_fields = pointer(e1ap_cuup_bearer_ctx_setup_msg)
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 297
try:
    e1ap_cuup_bearer_ctx_release_fields = pointer(e1ap_cuup_bearer_ctx_release_msg)
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 298
try:
    nssai_t_fields = pointer(nssai_t_msg)
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 299
try:
    cucp_pdu_session_bearer_add_modify_fields = pointer(cucp_pdu_session_bearer_add_modify_msg)
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 300
try:
    cucp_pdu_session_remove_fields = pointer(cucp_pdu_session_remove_msg)
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 303
try:
    UE_CONTEXTS_PB_H_MAX_SIZE = cucp_pdu_session_bearer_add_modify_size
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 304
try:
    cucp_pdu_session_bearer_add_modify_size = 48
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 305
try:
    cucp_pdu_session_remove_size = 28
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 306
try:
    cucp_ue_ctx_creation_size = 35
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 307
try:
    cucp_ue_ctx_deletion_size = 17
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 308
try:
    cucp_ue_ctx_update_size = 35
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 309
try:
    du_ue_ctx_creation_size = 47
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 310
try:
    du_ue_ctx_deletion_size = 17
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 311
try:
    du_ue_ctx_update_crnti_size = 23
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 312
try:
    e1ap_cucp_bearer_ctx_setup_size = 23
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 313
try:
    e1ap_cuup_bearer_ctx_release_size = 31
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 314
try:
    e1ap_cuup_bearer_ctx_setup_size = 31
except:
    pass

# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 315
try:
    nssai_t_size = 12
except:
    pass

_du_ue_ctx_creation = struct__du_ue_ctx_creation# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 21

_du_ue_ctx_update_crnti = struct__du_ue_ctx_update_crnti# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 27

_du_ue_ctx_deletion = struct__du_ue_ctx_deletion# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 32

_cucp_ue_ctx_creation = struct__cucp_ue_ctx_creation# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 42

_cucp_ue_ctx_update = struct__cucp_ue_ctx_update# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 50

_cucp_ue_ctx_deletion = struct__cucp_ue_ctx_deletion# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 55

_e1ap_cucp_bearer_ctx_setup = struct__e1ap_cucp_bearer_ctx_setup# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 61

_e1ap_cuup_bearer_ctx_setup = struct__e1ap_cuup_bearer_ctx_setup# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 69

_e1ap_cuup_bearer_ctx_release = struct__e1ap_cuup_bearer_ctx_release# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 77

_nssai_t = struct__nssai_t# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 82

_cucp_pdu_session_bearer_add_modify = struct__cucp_pdu_session_bearer_add_modify# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 90

_cucp_pdu_session_remove = struct__cucp_pdu_session_remove# /home/maxim/Desktop/jrtc-apps/codelets/ue_contexts/ue_contexts.pb.h: 96

# No inserted files

# No prefix-stripping

