# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
"""Test install action

"""

import logging
import os

from os.path import (
    join as opj,
    isdir,
    exists,
    basename,
    dirname,
)
from unittest.mock import patch
from datalad.api import (
    create,
    install,
    get,
)
from datalad.utils import (
    chpwd,
    on_windows,
    getpwd,
    _path_,
    rmtree,
    Path,
)
from datalad.support import path as op
from datalad.interface.results import YieldDatasets
from datalad.support.exceptions import (
    InsufficientArgumentsError,
    IncompleteResultsError,
)
from datalad.support.gitrepo import GitRepo
from datalad.support.annexrepo import AnnexRepo
from datalad.cmd import WitlessRunner as Runner
from datalad.tests.utils import (
    skip_ssh,
    create_tree,
    with_tempfile,
    assert_in,
    with_tree,
    with_testrepos,
    eq_,
    ok_,
    assert_false,
    ok_file_has_content,
    assert_not_in,
    assert_raises,
    assert_is_instance,
    assert_repo_status,
    assert_result_count,
    assert_status,
    assert_in_results,
    DEFAULT_BRANCH,
    ok_startswith,
    serve_path_via_http,
    swallow_logs,
    use_cassette,
    skip_if_no_network,
    skip_if_on_windows,
    put_file_under_git,
    integration,
    slow,
    usecase,
    get_datasets_topdir,
    known_failure_windows,
    known_failure_githubci_win,
)
from ..dataset import Dataset

###############
# Test helpers:
###############


@with_tree(tree={'file.txt': '123'})
@serve_path_via_http
@with_tempfile
def _test_guess_dot_git(annex, path, url, tdir):
    repo = (AnnexRepo if annex else GitRepo)(path, create=True)
    repo.add('file.txt', git=not annex)
    repo.commit()

    # we need to prepare to be served via http, otherwise it must fail
    with swallow_logs() as cml:
        assert_raises(IncompleteResultsError, install, path=tdir, source=url)
    ok_(not exists(tdir))

    Runner(cwd=path).run(['git', 'update-server-info'])

    with swallow_logs() as cml:
        installed = install(tdir, source=url)
        assert_not_in("Failed to get annex.uuid", cml.out)
    eq_(installed.pathobj.resolve(), Path(tdir).resolve())
    ok_(exists(tdir))
    assert_repo_status(tdir, annex=annex)


def test_guess_dot_git():
    for annex in False, True:
        yield _test_guess_dot_git, annex


######################
# Test actual Install:
######################

def test_insufficient_args():
    assert_raises(InsufficientArgumentsError, install)
    assert_raises(InsufficientArgumentsError, install, description="some")
    assert_raises(InsufficientArgumentsError, install, None)
    assert_raises(InsufficientArgumentsError, install, None, description="some")

# ValueError: path is on mount 'D:', start on mount 'C:
@known_failure_githubci_win
@with_tempfile(mkdir=True)
def test_invalid_args(path):
    assert_raises(IncompleteResultsError, install, 'Zoidberg', source='Zoidberg')
    # install to an invalid URL
    assert_raises(ValueError, install, 'ssh://mars:Zoidberg', source='Zoidberg')
    # install to a remote location
    assert_raises(ValueError, install, 'ssh://mars/Zoidberg', source='Zoidberg')
    # make fake dataset
    ds = create(path)
    assert_raises(IncompleteResultsError, install, '/higherup.', 'Zoidberg', dataset=ds)


# This test caused a mysterious segvault in gh-1350. I reimplementation of
# the same test functionality in test_clone.py:test_clone_crcns that uses
# `clone` instead of `install` passes without showing this behavior
# This test is disabled until some insight into the cause of the issue
# materializes.
#@skip_if_no_network
#@use_cassette('test_install_crcns')
#@with_tempfile(mkdir=True)
#@with_tempfile(mkdir=True)
#def test_install_crcns(tdir, ds_path):
#    with chpwd(tdir):
#        with swallow_logs(new_level=logging.INFO) as cml:
#            install("all-nonrecursive", source='///')
#            # since we didn't log decorations such as log level atm while
#            # swallowing so lets check if exit code is returned or not
#            # I will test both
#            assert_not_in('ERROR', cml.out)
#            # below one must not fail alone! ;)
#            assert_not_in('with exit code', cml.out)
#
#        # should not hang in infinite recursion
#        with chpwd('all-nonrecursive'):
#            get("crcns")
#        ok_(exists(_path_("all-nonrecursive/crcns/.git/config")))
#        # and we could repeat installation and get the same result
#        ds1 = install(_path_("all-nonrecursive/crcns"))
#        ok_(ds1.is_installed())
#        ds2 = Dataset('all-nonrecursive').install('crcns')
#        eq_(ds1, ds2)
#        eq_(ds1.path, ds2.path)  # to make sure they are a single dataset
#
#    # again, but into existing dataset:
#    ds = create(ds_path)
#    crcns = ds.install("///crcns")
#    ok_(crcns.is_installed())
#    eq_(crcns.path, opj(ds_path, "crcns"))
#    assert_in(crcns.path, ds.get_subdatasets(absolute=True))


@skip_if_no_network
@use_cassette('test_install_crcns')
@with_tree(tree={'sub': {}})
def test_install_datasets_root(tdir):
    with chpwd(tdir):
        ds = install("///")
        ok_(ds.is_installed())
        eq_(ds.path, opj(tdir, get_datasets_topdir()))

        # do it a second time:
        result = install("///", result_xfm=None, return_type='list')
        assert_status('notneeded', result)
        eq_(YieldDatasets()(result[0]), ds)

        # and a third time into an existing something, that is not a dataset:
        with open(opj(tdir, 'sub', 'a_file.txt'), 'w') as f:
            f.write("something")

        with assert_raises(IncompleteResultsError) as cme:
            install("sub", source='///')
        assert_in("already exists and not empty", str(cme.exception))


# https://github.com/datalad/datalad/pull/3975/checks?check_run_id=369789022#step:8:360
@known_failure_windows
@with_testrepos('.*basic.*', flavors=['local-url', 'network', 'local'])
@with_tempfile(mkdir=True)
def test_install_simple_local(src, path):
    origin = Dataset(path)

    # now install it somewhere else
    ds = install(path, source=src, description='mydummy')
    eq_(ds.path, path)
    ok_(ds.is_installed())
    if not isinstance(origin.repo, AnnexRepo):
        # this means it is a GitRepo
        ok_(isinstance(origin.repo, GitRepo))
        # stays plain Git repo
        ok_(isinstance(ds.repo, GitRepo))
        ok_(not isinstance(ds.repo, AnnexRepo))
        ok_(GitRepo.is_valid_repo(ds.path))
        eq_(set(ds.repo.get_indexed_files()),
            {'test.dat', 'INFO.txt'})
        assert_repo_status(path, annex=False)
    else:
        # must be an annex
        ok_(isinstance(ds.repo, AnnexRepo))
        ok_(AnnexRepo.is_valid_repo(ds.path, allow_noninitialized=False))
        eq_(set(ds.repo.get_indexed_files()),
            {'test.dat', 'INFO.txt', 'test-annex.dat'})
        assert_repo_status(path, annex=True)
        # no content was installed:
        ok_(not ds.repo.file_has_content('test-annex.dat'))
        uuid_before = ds.repo.uuid
        ok_(uuid_before)  # we actually have an uuid
        eq_(ds.repo.get_description(), 'mydummy')

    # installing it again, shouldn't matter:
    res = install(path, source=src, result_xfm=None, return_type='list')
    assert_status('notneeded', res)
    ok_(ds.is_installed())
    if isinstance(origin.repo, AnnexRepo):
        eq_(uuid_before, ds.repo.uuid)


# https://github.com/datalad/datalad/pull/3975/checks?check_run_id=369789022#step:8:298
@known_failure_windows
@with_testrepos(flavors=['local-url', 'network', 'local'])
@with_tempfile
def test_install_dataset_from_just_source(url, path):
    with chpwd(path, mkdir=True):
        ds = install(source=url)

    ok_startswith(ds.path, path)
    ok_(ds.is_installed())
    ok_(GitRepo.is_valid_repo(ds.path))
    assert_repo_status(ds.path, annex=None)
    assert_in('INFO.txt', ds.repo.get_indexed_files())


@slow   # 25sec on Yarik's laptop
@with_testrepos(flavors=['local'])
@with_tempfile(mkdir=True)
def test_install_dataset_from_instance(src, dst):
    origin = Dataset(src)
    clone = install(source=origin, path=dst)

    assert_is_instance(clone, Dataset)
    ok_startswith(clone.path, dst)
    ok_(clone.is_installed())
    ok_(GitRepo.is_valid_repo(clone.path))
    assert_repo_status(clone.path, annex=None)
    assert_in('INFO.txt', clone.repo.get_indexed_files())


@known_failure_githubci_win
@with_testrepos(flavors=['network'])
@with_tempfile
def test_install_dataset_from_just_source_via_path(url, path):
    # for remote urls only, the source could be given to `path`
    # to allows for simplistic cmdline calls
    # Q (ben): remote urls only? Sure? => TODO

    with chpwd(path, mkdir=True):
        ds = install(url)

    ok_startswith(ds.path, path)
    ok_(ds.is_installed())
    ok_(GitRepo.is_valid_repo(ds.path))
    assert_repo_status(ds.path, annex=None)
    assert_in('INFO.txt', ds.repo.get_indexed_files())


@with_tree(tree={
    'ds': {'test.txt': 'some'},
    })
@serve_path_via_http
@with_tempfile(mkdir=True)
def test_install_dataladri(src, topurl, path):
    # make plain git repo
    ds_path = opj(src, 'ds')
    gr = GitRepo(ds_path, create=True)
    gr.add('test.txt')
    gr.commit('demo')
    Runner(cwd=gr.path).run(['git', 'update-server-info'])
    # now install it somewhere else
    with patch('datalad.consts.DATASETS_TOPURL', topurl), \
            swallow_logs():
        ds = install(path, source='///ds')
    eq_(ds.path, path)
    assert_repo_status(path, annex=False)
    ok_file_has_content(opj(path, 'test.txt'), 'some')


@slow   # 46sec on Yarik's laptop and tripped Travis CI
@with_testrepos('submodule_annex', flavors=['local', 'local-url', 'network'])
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_install_recursive(src, path_nr, path_r):
    # first install non-recursive:
    ds = install(path_nr, source=src, recursive=False)
    ok_(ds.is_installed())
    for sub in ds.subdatasets(recursive=True, result_xfm='datasets'):
        ok_(not sub.is_installed(),
            "Unintentionally installed: %s" % (sub,))
    # this also means, subdatasets to be listed as not fulfilled:
    eq_(set(ds.subdatasets(recursive=True, fulfilled=False, result_xfm='relpaths')),
        {'subm 1', '2'})

    # now recursively:
    # don't filter implicit results so we can inspect them
    res = install(path_r, source=src, recursive=True,
                  result_xfm=None, result_filter=None)
    # installed a dataset and two subdatasets
    assert_result_count(res, 3, action='install', type='dataset')
    # we recurse top down during installation, so toplevel should appear at
    # first position in returned list
    eq_(res[0]['path'], path_r)
    top_ds = Dataset(res[0]['path'])
    ok_(top_ds.is_installed())

    # the subdatasets are contained in returned list:
    # (Note: Until we provide proper (singleton) instances for Datasets,
    # need to check for their paths)
    assert_in_results(res, path=opj(top_ds.path, 'subm 1'), type='dataset')
    assert_in_results(res, path=opj(top_ds.path, '2'), type='dataset')

    eq_(len(top_ds.subdatasets(recursive=True)), 2)

    for subds in top_ds.subdatasets(recursive=True, result_xfm='datasets'):
        ok_(subds.is_installed(),
            "Not installed: %s" % (subds,))
        # no content was installed:
        ainfo = subds.repo.get_content_annexinfo(init=None,
                                                 eval_availability=True)
        assert_false(any(st["has_content"] for st in ainfo.values()))
    # no unfulfilled subdatasets:
    ok_(top_ds.subdatasets(recursive=True, fulfilled=False) == [])

    # check if we can install recursively into a dataset
    # https://github.com/datalad/datalad/issues/2982
    subds = ds.install('recursive-in-ds', source=src, recursive=True)
    ok_(subds.is_installed())
    for subsub in subds.subdatasets(recursive=True, result_xfm='datasets'):
        ok_(subsub.is_installed())

    # check that we get subdataset instances manufactored from notneeded results
    # to install existing subdatasets again
    eq_(subds, ds.install('recursive-in-ds'))


@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
def test_install_recursive_with_data(src, path):

    # now again; with data:
    res = install(path, source=src, recursive=True, get_data=True,
                  result_filter=None, result_xfm=None)
    assert_status('ok', res)
    # installed a dataset and two subdatasets, and one file with content in
    # each
    assert_result_count(res, 3, type='dataset', action='install')
    assert_result_count(res, 3, type='file', action='get')
    # we recurse top down during installation, so toplevel should appear at
    # first position in returned list
    eq_(res[0]['path'], path)
    top_ds = YieldDatasets()(res[0])
    ok_(top_ds.is_installed())

    def all_have_content(repo):
        ainfo = repo.get_content_annexinfo(init=None, eval_availability=True)
        return all(st["has_content"] for st in ainfo.values())

    if isinstance(top_ds.repo, AnnexRepo):
        ok_(all_have_content(top_ds.repo))

    for subds in top_ds.subdatasets(recursive=True, result_xfm='datasets'):
        ok_(subds.is_installed(), "Not installed: %s" % (subds,))
        if isinstance(subds.repo, AnnexRepo):
            ok_(all_have_content(subds.repo))


# https://github.com/datalad/datalad/pull/3975/checks?check_run_id=369789022#step:8:555
@known_failure_windows
@slow  # 88.0869s  because of going through multiple test repos, ~8sec each time
@with_testrepos('.*annex.*', flavors=['local'])
# 'local-url', 'network'
# TODO: Somehow annex gets confused while initializing installed ds, whose
# .git/config show a submodule url "file:///aaa/bbb%20b/..."
# this is delivered by with_testrepos as the url to clone
@with_tempfile
def test_install_into_dataset(source, top_path):

    ds = create(top_path)
    assert_repo_status(ds.path)

    subds = ds.install("sub", source=source)
    ok_(isdir(opj(subds.path, '.git')))
    ok_(subds.is_installed())
    assert_in('sub', ds.subdatasets(result_xfm='relpaths'))
    # sub is clean:
    assert_repo_status(subds.path, annex=None)
    # top is too:
    assert_repo_status(ds.path, annex=None)
    ds.save(message='addsub')
    # now it is:
    assert_repo_status(ds.path, annex=None)

    # but we could also save while installing and there should be no side-effect
    # of saving any other changes if we state to not auto-save changes
    # Create a dummy change
    create_tree(ds.path, {'dummy.txt': 'buga'})
    assert_repo_status(ds.path, untracked=['dummy.txt'])
    subds_ = ds.install("sub2", source=source)
    eq_(subds_.path, opj(ds.path, "sub2"))  # for paranoid yoh ;)
    assert_repo_status(ds.path, untracked=['dummy.txt'])

    # and we should achieve the same behavior if we create a dataset
    # and then decide to add it
    create(_path_(top_path, 'sub3'))
    assert_repo_status(ds.path, untracked=['dummy.txt', 'sub3/'])
    ds.save('sub3')
    assert_repo_status(ds.path, untracked=['dummy.txt'])


@slow   # 15sec on Yarik's laptop
@known_failure_windows  #FIXME
@usecase  # 39.3074s
@skip_if_no_network
@use_cassette('test_install_crcns')
@with_tempfile
def test_failed_install_multiple(top_path):
    ds = create(top_path)

    create(_path_(top_path, 'ds1'))
    create(_path_(top_path, 'ds3'))
    assert_repo_status(ds.path, annex=None, untracked=['ds1/', 'ds3/'])

    # specify install with multiple paths and one non-existing
    with assert_raises(IncompleteResultsError) as cme:
        ds.install(['ds1', 'ds2', '///crcns', '///nonexisting', 'ds3'],
                   on_failure='continue')

    # install doesn't add existing submodules -- add does that
    assert_repo_status(ds.path, annex=None, untracked=['ds1/', 'ds3/'])
    ds.save(['ds1', 'ds3'])
    assert_repo_status(ds.path, annex=None)
    # those which succeeded should be saved now
    eq_(ds.subdatasets(result_xfm='relpaths'), ['crcns', 'ds1', 'ds3'])
    # and those which didn't -- listed
    eq_(set(r.get('source_url', r['path']) for r in cme.exception.failed),
        {'///nonexisting', _path_(top_path, 'ds2')})


# https://github.com/datalad/datalad/pull/3975/checks?check_run_id=369789022#step:8:318
@known_failure_windows
@with_testrepos('submodule_annex', flavors=['local', 'local-url', 'network'])
@with_tempfile(mkdir=True)
def test_install_known_subdataset(src, path):

    # get the superdataset:
    ds = install(path, source=src)
    # subdataset not installed:
    subds = Dataset(opj(path, 'subm 1'))
    assert_false(subds.is_installed())
    assert_in('subm 1', ds.subdatasets(fulfilled=False, result_xfm='relpaths'))
    assert_not_in('subm 1', ds.subdatasets(fulfilled=True, result_xfm='relpaths'))
    # install it:
    ds.install('subm 1')
    ok_(subds.is_installed())
    ok_(AnnexRepo.is_valid_repo(subds.path, allow_noninitialized=False))
    # Verify that it is the correct submodule installed and not
    # new repository initiated
    eq_(set(subds.repo.get_indexed_files()),
        {'test.dat', 'INFO.txt', 'test-annex.dat'})
    assert_not_in('subm 1', ds.subdatasets(fulfilled=False, result_xfm='relpaths'))
    assert_in('subm 1', ds.subdatasets(fulfilled=True, result_xfm='relpaths'))

    # now, get the data by reinstalling with -g:
    ok_(subds.repo.file_has_content('test-annex.dat') is False)
    with chpwd(ds.path):
        result = get(path='subm 1', dataset=os.curdir)
        assert_in_results(result, path=opj(subds.path, 'test-annex.dat'))
        ok_(subds.repo.file_has_content('test-annex.dat') is True)
        ok_(subds.is_installed())


@slow  # 46.3650s
@with_tempfile(mkdir=True)
@with_tempfile(mkdir=True)
def test_implicit_install(src, dst):

    origin_top = create(src)
    origin_sub = origin_top.create("sub")
    origin_subsub = origin_sub.create("subsub")
    with open(opj(origin_top.path, "file1.txt"), "w") as f:
        f.write("content1")
    origin_top.save("file1.txt")
    with open(opj(origin_sub.path, "file2.txt"), "w") as f:
        f.write("content2")
    origin_sub.save("file2.txt")
    with open(opj(origin_subsub.path, "file3.txt"), "w") as f:
        f.write("content3")
    origin_subsub.save("file3.txt")
    origin_top.save(recursive=True)

    # first, install toplevel:
    ds = install(dst, source=src)
    ok_(ds.is_installed())

    sub = Dataset(opj(ds.path, "sub"))
    ok_(not sub.is_installed())
    subsub = Dataset(opj(sub.path, "subsub"))
    ok_(not subsub.is_installed())

    # fail on obscure non-existing one
    assert_raises(IncompleteResultsError, ds.install, source='obscure')

    # install 3rd level and therefore implicitly the 2nd:
    result = ds.install(path=opj("sub", "subsub"))
    ok_(sub.is_installed())
    ok_(subsub.is_installed())
    # but by default implicit results are not reported
    eq_(result, subsub)

    # fail on obscure non-existing one in subds
    assert_raises(IncompleteResultsError, ds.install, source=opj('sub', 'obscure'))

    # clean up, the nasty way
    rmtree(dst, chmod_files=True)
    ok_(not exists(dst))

    # again first toplevel:
    ds = install(dst, source=src)
    ok_(ds.is_installed())
    sub = Dataset(opj(ds.path, "sub"))
    ok_(not sub.is_installed())
    subsub = Dataset(opj(sub.path, "subsub"))
    ok_(not subsub.is_installed())

    # now implicit but without an explicit dataset to install into
    # (deriving from CWD):
    with chpwd(dst):
        # don't ask for the file content to make return value comparison
        # simpler
        result = get(path=opj("sub", "subsub"), get_data=False, result_xfm='datasets')
        ok_(sub.is_installed())
        ok_(subsub.is_installed())
        eq_(result, [sub, subsub])


@with_tempfile(mkdir=True)
def test_failed_install(dspath):
    ds = create(dspath)
    assert_raises(IncompleteResultsError,
                  ds.install,
                  "sub",
                  source="http://nonexistingreallyanything.datalad.org/bla")


@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
def test_install_list(path, top_path):

    # we want to be able to install several things, if these are known
    # (no 'source' allowed). Therefore first toplevel:
    ds = install(top_path, source=path, recursive=False)
    assert_not_in('annex.hardlink', ds.config)
    ok_(ds.is_installed())
    sub1 = Dataset(opj(top_path, 'subm 1'))
    sub2 = Dataset(opj(top_path, '2'))
    ok_(not sub1.is_installed())
    ok_(not sub2.is_installed())

    # fails, when `source` is passed:
    assert_raises(ValueError, ds.install,
                  path=['subm 1', '2'],
                  source='something')

    # now should work:
    result = ds.install(path=['subm 1', '2'], result_xfm='paths')
    ok_(sub1.is_installed())
    ok_(sub2.is_installed())
    eq_(set(result), {sub1.path, sub2.path})
    # and if we request it again via get, result should be empty
    get_result = ds.get(path=['subm 1', '2'], get_data=False)
    assert_status('notneeded', get_result)


@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
def test_reckless(path, top_path):
    ds = install(top_path, source=path, reckless=True)
    eq_(ds.config.get('annex.hardlink', None), 'true')
    eq_(ds.repo.repo_info()['untrusted repositories'][0]['here'], True)


@with_tree(tree={'top_file.txt': 'some',
                 'sub 1': {'sub1file.txt': 'something else',
                           'subsub': {'subsubfile.txt': 'completely different',
                                      }
                           },
                 'sub 2': {'sub2file.txt': 'meaningless',
                           }
                 })
@with_tempfile(mkdir=True)
@skip_if_on_windows  # Due to "another process error"
def test_install_recursive_repeat(src, path):
    top_src = Dataset(src).create(force=True)
    sub1_src = top_src.create('sub 1', force=True)
    sub2_src = top_src.create('sub 2', force=True)
    subsub_src = sub1_src.create('subsub', force=True)
    top_src.save(recursive=True)
    assert_repo_status(top_src.path)

    # install top level:
    top_ds = install(path, source=src)
    ok_(top_ds.is_installed() is True)
    sub1 = Dataset(opj(path, 'sub 1'))
    ok_(sub1.is_installed() is False)
    sub2 = Dataset(opj(path, 'sub 2'))
    ok_(sub2.is_installed() is False)
    subsub = Dataset(opj(path, 'sub 1', 'subsub'))
    ok_(subsub.is_installed() is False)

    # install again, now with data and recursive, but recursion_limit 1:
    result = get(path, dataset=path, recursive=True, recursion_limit=1,
                 result_xfm='datasets')
    # top-level dataset was not reobtained
    assert_not_in(top_ds, result)
    assert_in(sub1, result)
    assert_in(sub2, result)
    assert_not_in(subsub, result)
    ok_(top_ds.repo.file_has_content('top_file.txt') is True)
    ok_(sub1.repo.file_has_content('sub1file.txt') is True)
    ok_(sub2.repo.file_has_content('sub2file.txt') is True)

    # install sub1 again, recursively and with data
    top_ds.install('sub 1', recursive=True, get_data=True)
    ok_(subsub.is_installed())
    ok_(subsub.repo.file_has_content('subsubfile.txt'))


@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
@with_tempfile
def test_install_skip_list_arguments(src, path, path_outside):
    ds = install(path, source=src)
    ok_(ds.is_installed())

    # install a list with valid and invalid items:
    result = ds.install(
        path=['subm 1', 'not_existing', path_outside, '2'],
        get_data=False,
        on_failure='ignore', result_xfm=None, return_type='list')
    # good and bad results together
    ok_(isinstance(result, list))
    eq_(len(result), 4)
    # check that we have an 'impossible/error' status for both invalid args
    # but all the other tasks have been accomplished
    assert_result_count(
        result, 1, status='impossible', message="path does not exist",
        path=opj(ds.path, 'not_existing'))
    assert_result_count(
        result, 1, status='error',
        message=("path not associated with dataset %s", ds),
        path=path_outside)
    for sub in [Dataset(opj(path, 'subm 1')), Dataset(opj(path, '2'))]:
        assert_result_count(
            result, 1, status='ok',
            message=('Installed subdataset in order to get %s', sub.path))
        ok_(sub.is_installed())

    # return of get is always a list, by default, even if just one thing was gotten
    # in this case 'subm1' was already obtained above, so this will get this
    # content of the subdataset
    with assert_raises(IncompleteResultsError) as cme:
        ds.install(path=['subm 1', 'not_existing'])
    with assert_raises(IncompleteResultsError) as cme:
        ds.get(path=['subm 1', 'not_existing'])


@with_testrepos('submodule_annex', flavors=['local'])
@with_tempfile(mkdir=True)
def test_install_skip_failed_recursive(src, path):

    # install top level:
    ds = install(path, source=src)
    sub1 = Dataset(opj(path, 'subm 1'))
    sub2 = Dataset(opj(path, '2'))
    # sabotage recursive installation of 'subm 1' by polluting the target:
    with open(opj(path, 'subm 1', 'blocking.txt'), "w") as f:
        f.write("sdfdsf")

    with swallow_logs(new_level=logging.WARNING) as cml:
        result = ds.get(
            os.curdir, recursive=True,
            on_failure='ignore', result_xfm=None)
        # toplevel dataset was in the house already
        assert_result_count(
            result, 0, path=ds.path, type='dataset')
        # subm 1 should fail to install. [1] since comes after '2' submodule
        assert_in_results(
            result, status='error', path=sub1.path, type='dataset',
            message='target path already exists and not empty, refuse to '
                    'clone into target path')
        assert_in_results(result, status='ok', path=sub2.path)


@with_tree(tree={'top_file.txt': 'some',
                 'sub 1': {'sub1file.txt': 'something else',
                           'subsub': {'subsubfile.txt': 'completely different',
                                      }
                           },
                 'sub 2': {'sub2file.txt': 'meaningless',
                           }
                 })
@with_tempfile(mkdir=True)
def test_install_noautoget_data(src, path):
    subsub_src = Dataset(opj(src, 'sub 1', 'subsub')).create(force=True)
    sub1_src = Dataset(opj(src, 'sub 1')).create(force=True)
    sub2_src = Dataset(opj(src, 'sub 2')).create(force=True)
    top_src = Dataset(src).create(force=True)
    top_src.save(recursive=True)

    # install top level:
    # don't filter implicitly installed subdataset to check them for content
    cdss = install(path, source=src, recursive=True, result_filter=None)
    # there should only be datasets in the list of installed items,
    # and none of those should have any data for their annexed files yet
    for ds in cdss:
        ainfo = ds.repo.get_content_annexinfo(init=None,
                                              eval_availability=True)
        assert_false(any(st["has_content"] for st in ainfo.values()))


@with_tempfile
@with_tempfile
def test_install_source_relpath(src, dest):
    ds1 = create(src)
    src_ = basename(src)
    with chpwd(dirname(src)):
        ds2 = install(dest, source=src_)


@known_failure_windows  #FIXME
@integration  # 41.2043s
@with_tempfile
@with_tempfile
@with_tempfile
@with_tempfile
def test_install_consistent_state(src, dest, dest2, dest3):
    # if we install a dataset, where sub-dataset "went ahead" in that branch,
    # while super-dataset was not yet updated (e.g. we installed super before)
    # then it is desired to get that default installed branch to get to the
    # position where previous location was pointing to.
    # It is indeed a mere heuristic which might not hold the assumption in some
    # cases, but it would work for most simple and thus mostly used ones
    ds1 = create(src)
    sub1 = ds1.create('sub1')

    def check_consistent_installation(ds):
        datasets = [ds] + list(
            map(Dataset, ds.subdatasets(recursive=True, fulfilled=True,
                                        result_xfm='paths')))
        assert len(datasets) == 2  # in this test
        for ds in datasets:
            # all of them should be in the default branch
            eq_(ds.repo.get_active_branch(), DEFAULT_BRANCH)
            # all of them should be clean, so sub should be installed in a "version"
            # as pointed by the super
            ok_(not ds.repo.dirty)

    dest_ds = install(dest, source=src)
    # now we progress sub1 by adding sub2
    subsub2 = sub1.create('sub2')

    # and progress subsub2 forward to stay really thorough
    put_file_under_git(subsub2.path, 'file.dat', content="data")
    subsub2.save(message="added a file")  # above function does not commit

    # just installing a submodule -- apparently different code/logic
    # but also the same story should hold - we should install the version pointed
    # by the super, and stay all clean
    dest_sub1 = dest_ds.install('sub1')
    check_consistent_installation(dest_ds)

    # So now we have source super-dataset "dirty" with sub1 progressed forward
    # Our install should try to "retain" consistency of the installation
    # whenever possible.

    # install entire hierarchy without specifying dataset
    # no filter, we want full report
    dest2_ds = install(dest2, source=src, recursive=True, result_filter=None)
    check_consistent_installation(dest2_ds[0])  # [1] is the subdataset

    # install entire hierarchy by first installing top level ds
    # and then specifying sub-dataset
    dest3_ds = install(dest3, source=src, recursive=False)
    # and then install both submodules recursively while pointing
    # to it based on dest3_ds
    dest3_ds.install('sub1', recursive=True)
    check_consistent_installation(dest3_ds)

    # TODO: makes a nice use-case for an update operation


@skip_ssh
@with_tempfile
@with_tempfile
def test_install_subds_with_space(opath, tpath):
    ds = create(opath)
    ds.create('sub ds')
    # works even now, boring
    # install(tpath, source=opath, recursive=True)
    if on_windows:
        # on windows we cannot simply prepend datalad-test: to a path
        # and get a working sshurl...
        install(tpath, source=opath, recursive=True)
    else:
        # do via ssh!
        install(tpath, source="datalad-test:" + opath, recursive=True)
    assert Dataset(opj(tpath, 'sub ds')).is_installed()


# https://github.com/datalad/datalad/issues/2232
@with_tempfile
@with_tempfile
def test_install_from_tilda(opath, tpath):
    ds = create(opath)
    ds.create('sub ds')
    orelpath = os.path.join(
        '~',
        os.path.relpath(opath, os.path.expanduser('~'))
    )
    assert orelpath.startswith('~')  # just to make sure no normalization
    install(tpath, source=orelpath, recursive=True)
    assert Dataset(opj(tpath, 'sub ds')).is_installed()


@skip_if_on_windows  # create_sibling incompatible with win servers
@skip_ssh
@usecase
@with_tempfile(mkdir=True)
def test_install_subds_from_another_remote(topdir):
    # https://github.com/datalad/datalad/issues/1905
    from datalad.support.network import PathRI
    with chpwd(topdir):
        origin_ = 'origin'
        clone1_ = 'clone1'
        clone2_ = 'clone2'

        origin = create(origin_, annex=False)
        clone1 = install(source=origin, path=clone1_)
        # print("Initial clone")
        clone1.create_sibling('ssh://datalad-test%s/%s' % (PathRI(getpwd()).posixpath, clone2_), name=clone2_)

        # print("Creating clone2")
        clone1.publish(to=clone2_)
        clone2 = Dataset(clone2_)
        # print("Initiating subdataset")
        clone2.create('subds1')

        # print("Updating")
        clone1.update(merge=True, sibling=clone2_)
        # print("Installing within updated dataset -- should be able to install from clone2")
        clone1.install('subds1')


# Takes > 2 sec
# Do not use cassette
@skip_if_no_network
@with_tempfile
def check_datasets_datalad_org(suffix, tdir):
    # Test that git annex / datalad install, get work correctly on our datasets.datalad.org
    # Apparently things can break, especially with introduction of the
    # smart HTTP backend for apache2 etc
    ds = install(tdir, source='///dicoms/dartmouth-phantoms/bids_test6-PD+T2w' + suffix)
    eq_(ds.config.get('remote.origin.annex-ignore', None), None)
    # assert_result_count and not just assert_status since for some reason on
    # Windows we get two records due to a duplicate attempt (as res[1]) to get it
    # again, which is reported as "notneeded".  For the purpose of this test
    # it doesn't make a difference.
    assert_result_count(
        ds.get(op.join('001-anat-scout_ses-{date}', '000001.dcm')),
        1,
        status='ok')
    assert_status('ok', ds.remove())


def test_datasets_datalad_org():
    yield check_datasets_datalad_org, ''
    yield check_datasets_datalad_org, '/.git'


# https://github.com/datalad/datalad/issues/3469
@with_tempfile(mkdir=True)
def test_relpath_semantics(path):
    with chpwd(path):
        super = create('super')
        create('subsrc')
        sub = install(
            dataset='super', source='subsrc', path=op.join('super', 'sub'))
        eq_(sub.path, op.join(super.path, 'sub'))
