#!/usr/bin/env python
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the DataLad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

import platform

from glob import glob
from os.path import sep as pathsep, join as opj, dirname

from setuptools import setup, find_packages

# imports for manpage generation
import datetime
from distutils.command.build import build
from distutils.core import Command
import argparse

# This might entail lots of imports which might not yet be available
# so let's do ad-hoc parsing of the version.py
#import datalad.version
with open(opj(dirname(__file__), 'datalad', 'version.py')) as f:
    version_lines = list(filter(lambda x: x.startswith('__version__'), f))
assert(len(version_lines) == 1)
version = version_lines[0].split('=')[1].strip(" '\"\t\n")

# Only recentish versions of find_packages support include
# datalad_pkgs = find_packages('.', include=['datalad*'])
# so we will filter manually for maximal compatibility
datalad_pkgs = [pkg for pkg in find_packages('.') if pkg.startswith('datalad')]

# keyring is a tricky one since it got split into two as of 8.0 and on older
# systems there is a problem installing via pip (e.g. on wheezy) so for those we
# would just ask for keyring
keyring_requires = ['keyring>=8.0', 'keyrings.alt']
pbar_requires = ['tqdm']

dist = platform.dist()
# on oldstable Debian let's ask for lower versions and progressbar instead
if dist[0] == 'debian' and dist[1].split('.', 1)[0] == '7':
    keyring_requires = ['keyring<8.0']
    pbar_requires = ['progressbar']

requires = {
    'core': [
        'appdirs',
        'GitPython>=2.0',
        'humanize',
        'mock',  # mock is also used for auto.py, not only for testing
        'patool>=1.7',
        'six>=1.8.0',
    ] + pbar_requires,
    'downloaders': [
        'boto',
        'msgpack-python',
        'requests>=1.2',
    ] + keyring_requires,
    'crawl': [
        'scrapy>=1.1.0rc3',  # versioning is primarily for python3 support
    ],
    'tests': [
        'BeautifulSoup4',  # VERY weak requirement, still used in one of the tests
        'httpretty>=0.8.14',
        'mock',
        'nose>=1.3.4',
        'testtools',
        'vcrpy',
    ]
}
requires['full'] = sum(list(requires.values()), [])

#############################################################################
## Start of manpage generator code ##########################################
#############################################################################

# The BuildManPage code was originally distributed
# under the same License of Python
# Copyright (c) 2014 Oz Nahum Tiram  <nahumoz@gmail.com>

"""
Add a `build_manpage` command  to your setup.py.
To use this Command class import the class to your setup.py,
and add a command to call this class::

    from build_manpage import BuildManPage

    ...
    ...

    setup(
    ...
    ...
    cmdclass={
        'build_manpage': BuildManPage,
    )

You can then use the following setup command to produce a man page::

    $ python setup.py build_manpage --output=prog.1
        --parser=yourmodule:argparser

Alternatively, set the variable AUTO_BUILD to True, and just invoke::

    $ python setup.py build

If automatically want to build the man page every time you invoke your build,
add to your ```setup.cfg``` the following::

    [build_manpage]
    output = <appname>.1
    parser = <path_to_your_parser>
"""

build.sub_commands.append(('build_manpage', None))


class BuildManPage(Command):

    description = 'Generate man page from an ArgumentParser instance.'

    user_options = [
        ('output=', 'O', 'output file'),
        ('parser=', None, 'module path to an ArgumentParser instance'
         '(e.g. mymod:func, where func is a method or function which return'
         'an arparse.ArgumentParser instance.'),
    ]

    def initialize_options(self):
        self.output = None
        self.parser = None

    def finalize_options(self):
        if self.output is None:
            raise DistutilsOptionError('\'output\' option is required')
        if self.parser is None:
            raise DistutilsOptionError('\'parser\' option is required')
        mod_name, func_name = self.parser.split(':')
        fromlist = mod_name.split('.')
        try:
            mod = __import__(mod_name, fromlist=fromlist)
            self._parser = getattr(mod, func_name)(
                formatter_class=ManPageFormatter)

        except ImportError as err:
            raise err

        self.announce('Writing man page %s' % self.output)
        self._today = datetime.date.today()

    def run(self):

        dist = self.distribution
        homepage = dist.get_url()
        appname = self._parser.prog

        sections = {'authors': ("pwman3 was originally written by Ivan Kelly "
                                "<ivan@ivankelly.net>.\n pwman3 is now "
                                "maintained "
                                "by Oz Nahum <nahumoz@gmail.com>."),
                    'distribution': ("The latest version of {} may be "
                                     "downloaded from {}".format(appname,
                                                                 homepage))
                    }

        dist = self.distribution
        mpf = ManPageFormatter(appname,
                               desc=dist.get_description(),
                               long_desc=dist.get_long_description(),
                               ext_sections=sections)

        m = mpf.format_man_page(self._parser)

        with open(self.output, 'w') as f:
            f.write(m)


class ManPageFormatter(argparse.HelpFormatter):

    """
    Formatter class to create man pages.
    This class relies only on the parser, and not distutils.
    The following shows a scenario for usage::

        from pwman import parser_options
        from build_manpage import ManPageFormatter

        # example usage ...

        dist = distribution
        mpf = ManPageFormatter(appname,
                               desc=dist.get_description(),
                               long_desc=dist.get_long_description(),
                               ext_sections=sections)

        # parser is an ArgumentParser instance
        m = mpf.format_man_page(parsr)

        with open(self.output, 'w') as f:
            f.write(m)

    The last line would print all the options and help infomation wrapped with
    man page macros where needed.
    """

    def __init__(self,
                 prog,
                 indent_increment=2,
                 max_help_position=24,
                 width=None,
                 section=1,
                 desc=None,
                 long_desc=None,
                 ext_sections=None,
                 authors=None,
                 ):

        super(ManPageFormatter, self).__init__(prog)

        self._prog = prog
        self._section = 1
        self._today = datetime.date.today().strftime('%Y\\-%m\\-%d')
        self._desc = desc
        self._long_desc = long_desc
        self._ext_sections = ext_sections

    def _get_formatter(self, **kwargs):
        return self.formatter_class(prog=self.prog, **kwargs)

    def _markup(self, txt):
        return txt.replace('-', '\\-')

    def _underline(self, string):
        return "\\fI\\s-1" + string + "\\s0\\fR"

    def _bold(self, string):
        if not string.strip().startswith('\\fB'):
            string = '\\fB' + string
        if not string.strip().endswith('\\fR'):
            string = string + '\\fR'
        return string

    def _mk_synopsis(self, parser):
        self.add_usage(parser.usage, parser._actions,
                       parser._mutually_exclusive_groups, prefix='')
        usage = self._format_usage(None, parser._actions,
                                   parser._mutually_exclusive_groups, '')

        usage = usage.replace('%s ' % self._prog, '')
        usage = '.SH SYNOPSIS\n \\fB%s\\fR %s\n' % (self._markup(self._prog),
                                                    usage)
        return usage

    def _mk_title(self, prog):
        return '.TH {0} {1} {2}\n'.format(prog, self._section,
                                          self._today)

    def _make_name(self, parser):
        """
        this method is in consitent with others ... it relies on
        distribution
        """
        return '.SH NAME\n%s \\- %s\n' % (parser.prog,
                                          parser.description)

    def _mk_description(self):
        if self._long_desc:
            long_desc = self._long_desc.replace('\n', '\n.br\n')
            return '.SH DESCRIPTION\n%s\n' % self._markup(long_desc)
        else:
            return ''

    def _mk_footer(self, sections):
        if not hasattr(sections, '__iter__'):
            return ''

        footer = []
        for section, value in sections.items():
            part = ".SH {}\n {}".format(section.upper(), value)
            footer.append(part)

        return '\n'.join(footer)

    def format_man_page(self, parser):
        page = []
        page.append(self._mk_title(self._prog))
        page.append(self._mk_synopsis(parser))
        page.append(self._mk_description())
        page.append(self._mk_options(parser))
        page.append(self._mk_footer(self._ext_sections))

        return ''.join(page)

    def _mk_options(self, parser):

        formatter = parser._get_formatter()

        # positionals, optionals and user-defined groups
        for action_group in parser._action_groups:
            formatter.start_section(None)
            formatter.add_text(None)
            formatter.add_arguments(action_group._group_actions)
            formatter.end_section()

        # epilog
        formatter.add_text(parser.epilog)

        # determine help from format above
        return '.SH OPTIONS\n' + formatter.format_help()

    def _format_action_invocation(self, action):
        if not action.option_strings:
            metavar, = self._metavar_formatter(action, action.dest)(1)
            return metavar

        else:
            parts = []

            # if the Optional doesn't take a value, format is:
            #    -s, --long
            if action.nargs == 0:
                parts.extend([self._bold(action_str) for action_str in
                              action.option_strings])

            # if the Optional takes a value, format is:
            #    -s ARGS, --long ARGS
            else:
                default = self._underline(action.dest.upper())
                args_string = self._format_args(action, default)
                for option_string in action.option_strings:
                    parts.append('%s %s' % (self._bold(option_string),
                                            args_string))

            return ', '.join(parts)

#############################################################################
## End of manpage generator code ############################################
#############################################################################

setup(
    name="datalad",
    author="DataLad Team and Contributors",
    author_email="team@datalad.org",
    version=version,
    description="data distribution geared toward scientific datasets",
    packages=datalad_pkgs,
    install_requires=requires['core'] + requires['downloaders'],
    extras_require=requires,
    entry_points={
        'console_scripts': [
            'datalad=datalad.cmdline.main:main',
            'git-annex-remote-datalad-archives=datalad.customremotes.archives:main',
            'git-annex-remote-datalad=datalad.customremotes.datalad:main',
        ],
    },
    cmdclass={
        'build_manpage': BuildManPage
    },
    package_data={
        'datalad': [
            'resources/git_ssh.sh',
            'resources/sshserver_cleanup_after_publish.sh',
            'resources/sshserver_prepare_for_publish.sh',
        ] +
        [p.split(pathsep, 1)[1] for p in glob('datalad/downloaders/configs/*.cfg')]
    }
)
