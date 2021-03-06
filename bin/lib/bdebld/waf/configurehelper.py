"""Implement waf.configure operations.
"""

import os

from bdebld.meta import buildconfigfactory
from bdebld.meta import buildflagsparser
from bdebld.meta import optionsutil
from bdebld.meta import repocontextloader
from bdebld.meta import repocontextverifier


class ConfigureHelper(object):

    def __init__(self, ctx, ufid, uplid):
        self.ctx = ctx
        self.ufid = ufid
        self.uplid = uplid

    def configure(self):
        self.ctx.msg('Prefix', self.ctx.env['PREFIX'])
        self.ctx.msg('Uplid', self.uplid)
        self.ctx.msg('Ufid', self.ufid)
        if self.ctx.options.verbose >= 1:
            self.ctx.msg('OS type', self.uplid.os_type)
            self.ctx.msg('OS name', self.uplid.os_name)
            self.ctx.msg('CPU type', self.uplid.cpu_type)
            self.ctx.msg('OS version', self.uplid.os_ver)
            self.ctx.msg('Compiler type', self.uplid.comp_type)
            self.ctx.msg('Compiler version', self.uplid.comp_ver)

        loader = repocontextloader.RepoContextLoader(
            self.ctx.path.abspath(), self.ctx.start_msg, self.ctx.end_msg)

        loader.load()
        self.repo_context = loader.repo_context

        if self.ctx.options.verify:
            self._verify()

        build_flags_parser = buildflagsparser.BuildFlagsParser(
            self.ctx.env['SHLIB_MARKER'],
            self.ctx.env['STLIB_MARKER'],
            self.ctx.env['LIB_ST'].replace('%s', r'([^ =]+)'),
            self.ctx.env['LIBPATH_ST'].replace('%s', r'([^ =]+)'),
            self.ctx.env['CPPPATH_ST'].replace('%s', r'([^ =]+)'),
            '/D' if self.uplid.comp_type == 'cl' else '-D')

        default_rules = optionsutil.get_default_option_rules()
        debug_opt_keys = self.ctx.options.debug_opt_keys.split(',') if \
            self.ctx.options.debug_opt_keys is not None else []
        self.build_config = buildconfigfactory.make_build_config(
            self.repo_context, build_flags_parser, self.uplid, self.ufid,
            default_rules, debug_opt_keys)

        def print_list(label, l):
            if len(l):
                self.ctx.msg(label, ','.join(sorted(l)))

        print_list('Configured package groups',
                   self.build_config.package_groups)
        print_list('Configured stand-alone packages',
                   self.build_config.sa_packages)
        print_list('Configured third-party packages',
                   self.build_config.third_party_packages)
        print_list('Loading external dependencies',
                   self.build_config.external_dep)

        if self.ctx.options.verbose >= 2:
            self.ctx.msg('Configuration details', self.build_config)

        self._configure_external_libs()
        self._save()

    def _verify(self):
        self.ctx.msg('Performing additional checks', '')
        verifier = repocontextverifier.RepoContextVerifier(
            self.repo_context, self.ctx.start_msg, self.ctx.end_msg)

        verifier.verify()
        if not verifier.is_success:
            self.ctx.fatal('Repo verification failed.')

    def _configure_external_libs(self):
        pkgconfig_args = ['--libs', '--cflags']

        if 'shr' not in self.ufid.flags:
            pkgconfig_args.append('--static')

        # If the static build is chosen (the default), waf assumes that all
        # libraries queried from pkg-config are to be built statically, which
        # is not true for some libraries. We work around this issue by manually
        # changing the affected libraries to be linked dynamically instead.
        dl_overrides = ['pthread', 'rt', 'nsl', 'socket']

        # If lib_suffix is set, we expect the pkgconfig files being depended on
        # to have the same suffix as well. Since the .dep files will not have
        # the suffix, we will remove the suffix from the names of the options
        # loaded into the waf environment.
        rename_keys = ['defines', 'includes', 'libpath', 'stlib', 'lib']
        lib_suffix = self.ctx.options.lib_suffix
        for lib in self.build_config.external_dep:
            actual_lib = lib + str(lib_suffix or '')
            self.ctx.check_cfg(
                package=actual_lib,
                args=pkgconfig_args,
                errmsg='Make sure the path indicated by environment variable '
                '"PKG_CONFIG_PATH" contains "%s.pc".  See config.log in '
                'the build output directory for more details.' % actual_lib)
            if lib_suffix:
                for k in rename_keys:
                    key_old = (k + '_' + actual_lib).upper()
                    key_new = (k + '_' + lib).upper()
                    self.ctx.env[key_new] = self.ctx.env[key_old]
                    del self.ctx.env[key_old]

            sl_key = ('stlib_' + lib).upper()
            dl_key = ('lib_' + lib).upper()

            # check_cfg always stores the libpath as dynamic library path
            # instead of static even if the configuration option is set to
            # static.
            if 'shr' not in self.ufid.flags:
                slp_key = ('stlibpath_' + lib).upper()
                dlp_key = ('libpath_' + lib).upper()
                if dlp_key in self.ctx.env:
                    self.ctx.env[slp_key] = self.ctx.env[dlp_key]
                    del self.ctx.env[dlp_key]

            # preserve the order of libraries
            for l in dl_overrides:
                if l in self.ctx.env[sl_key]:
                    if dl_key not in self.ctx.env:
                        self.ctx.env[dl_key] = []

                    self.ctx.env[sl_key].remove(l)
                    self.ctx.env[dl_key].append(l)

        if lib_suffix:
            defines_old = self.ctx.env['DEFINES']
            defines_new = []
            for d in defines_old:
                index = d.find('%s=1' % lib_suffix.upper())
                if index >= 0:
                    defines_new.append('%s=1' % d[0:index])
                else:
                    defines_new.append(d)

            self.ctx.env['DEFINES'] = defines_new

    def _get_pc_extra_include_dirs(self):
        include_dirs = os.environ.get('PC_EXTRA_INCLUDE_DIRS')
        if include_dirs:
            return include_dirs.split(':')
        return None

    def _save(self):
        self.ctx.env['build_config'] = self.build_config.to_pickle_str()
        self.ctx.env['install_flat_include'] = \
            self.ctx.options.install_flat_include
        self.ctx.env['install_lib_dir'] = self.ctx.options.install_lib_dir
        self.ctx.env['lib_suffix'] = self.ctx.options.lib_suffix
        self.ctx.env['pc_extra_include_dirs'] = \
            self._get_pc_extra_include_dirs()
        self.ctx.env['soname_overrides'] = self._get_soname_overrides()

        self._save_custom_waf_internals()

    def _get_soname_overrides(self):
        """Load custom SONAMEs from the envrionment.

        Sometimes we want to override the default SONAME used for a shared
        objects.  This can be done by setting a environment variable.

        E.g., we can set 'BDE_BSL_SONAME' to 'robo20150101bsl' to set the
        SONAME of the shared object built for the package group 'bsl'.
        """
        uor_names = list(self.build_config.sa_packages.keys()) + \
            list(self.build_config.package_groups.keys())

        soname_overrides = {}
        for name in uor_names:
            soname = os.environ.get('BDE_%s_SONAME' % name.upper())
            if soname:
                soname_overrides[name] = soname

        return soname_overrides

    def _save_custom_waf_internals(self):
        """Modify and save modifications to waf's internal variables.
        """

        # For visual studio, waf explicitly includes the system header files by
        # setting the 'INCLUDES' variable. BSL_OVERRIDE_STD mode requires that
        # the system header files, which contains the standard library, be
        # overridden with custom versions in bsl, so we workaround the issue by
        # moving the system includes to 'INCLUDE_BSL' if it exists. This
        # solution is not perfect, because it doesn't support package groups
        # that doesn't depend on bsl -- this is not a problem for BDE
        # libraries.

        if (self.uplid.os_type == 'windows' and
           'INCLUDES_BSL' in self.ctx.env):

            # Assume that 'INCLUDES' containly system header only.

            self.ctx.env['INCLUDES_BSL'].extend(self.ctx.env['INCLUDES'])
            del self.ctx.env['INCLUDES']

        if self.uplid.comp_type == 'xlc':

            # The default xlc linker options for linking shared objects for waf
            # are '-brtl' and '-bexpfull', bde_build does not use '-bexpfull',
            # change the options to preserve binary compatibility.

            self.ctx.env['LINKFLAGS_cxxshlib'] = ['-G', '-brtl']
            self.ctx.env['LINKFLAGS_cshlib'] = ['-G', '-brtl']

            # The envrionment variables SHLIB_MARKER and STLIB_MARKERS are used
            # by the '_parse_ldflags' function to determine wheter a library is
            # to be linked staticcally or dyanmically.  These are not set by
            # waf xlc plugin.
            self.ctx.env['SHLIB_MARKER'] = '-bdynamic'
            self.ctx.env['STLIB_MARKER'] = '-bstatic'

            # ar on aix only processes 32-bit object files by default
            if '64' in self.ufid.flags:
                self.ctx.env['ARFLAGS'] = ['-rcs', '-X64']

        if (self.uplid.os_name == 'sunos' and self.uplid.comp_type == 'cc'):

            # Work around bug in waf's sun CC plugin to allow for properly
            # adding SONAMES. TODO: submit patch
            self.ctx.env['SONAME_ST'] = '-h %s'
            self.ctx.env['DEST_BINFMT'] = 'elf'

            # Sun C++ linker  doesn't link in the Std library by default
            if 'shr' in self.ufid.flags:
                if 'LINKFLAGS' not in self.ctx.env:
                    self.ctx.env['LINKFLAGS'] = []
                self.ctx.env['LINKFLAGS'].extend(['-zdefs', '-lCstd', '-lCrun',
                                                  '-lc', '-lm', '-lsunmath',
                                                  '-lpthread'])

# -----------------------------------------------------------------------------
# Copyright 2015 Bloomberg Finance L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ----------------------------- END-OF-FILE -----------------------------------
