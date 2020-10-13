# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##

from time import sleep, time
from functools import partial

from datalad.support import path as op

# absolute import only to be able to run test without `nose` so to see progress bar
from datalad.support.parallel import (
    ProducerConsumer,
    no_parentds_in_futures,
)
from datalad.tests.utils import (
    assert_equal,
    assert_repo_status,
    assert_raises,
    rmtree,
    with_tempfile,
)

from datalad.support.exceptions import IncompleteResultsError

def test_ProducerConsumer():
    def slowprod(n, secs=0.1):
        for i in range(n):
            yield i
            sleep(secs)

    def slowcons(i):
        # so takes longer to consume than to produce and progress bar will appear
        # after slowprod is done producing
        #print(f"Consuming {i}")
        #t0 = time()
        sleep(0.2)
        #print(f"Consumed {i} in {time() - t0}")
        yield {
            "i": i, "status": "ok" if i % 2 else "error"
        }
    assert_equal(list(ProducerConsumer(
        slowprod(10),
        slowcons,
        jobs=10,
    )), [{"i": i, "status": "ok" if i % 2 else "error"} for i in range(10)])


@with_tempfile(mkdir=True)
def test_creatsubdatasets(topds_path, n=10):
    from datalad.distribution.dataset import Dataset
    from datalad.api import create
    ds = Dataset(topds_path).create()
    paths = [op.join(topds_path, "subds%d" % i) for i in range(n)]
    paths.extend(op.join(topds_path, "subds%d" % i, "subsub%d" %k) for i in range(n) for k in range(2))
    # To allow for parallel execution without hitting the problem of
    # a lock in the super dataset, we create all subdatasets, and then
    # save them all within their superdataset
    create_ = partial(create,  # cfg_proc="yoda",
                      result_xfm=None, return_type='generator')
    # if we flip the paths so to go from the end, create without --force should fail
    # and we should get the exception (the first one encountered!)
    # Note: reraise_immediately is of "concern" only for producer. since we typically
    # rely on outside code to do the killing!
    assert_raises(IncompleteResultsError, list, ProducerConsumer(paths[::-1], create_, jobs=5))
    # we are in a dirty state, let's just remove all those for a clean run
    rmtree(topds_path)

    # and this one followed by save should be good IFF we provide our dependency checker
    ds = Dataset(topds_path).create()
    list(ProducerConsumer(paths, create_, safe_to_consume=no_parentds_in_futures, jobs=10))
    ds.save(paths)
    assert_repo_status(ds.repo)


if __name__ == '__main__':
    # test_ProducerConsumer()
    test_creatsubdatasets()