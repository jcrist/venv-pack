from __future__ import print_function, division, absolute_import

import os

import pytest

test_dir = os.path.dirname(os.path.abspath(__file__))

rel_env_dir = os.path.join(test_dir, '..', '..', 'testing', 'environments')
env_dir = os.path.abspath(rel_env_dir)

simple_path = os.path.join(env_dir, 'simple')
editable_path = os.path.join(env_dir, 'editable')


def pytest_addoption(parser):
    parser.addoption(
        "--runslow", action="store_true", default=False, help="run slow tests"
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--runslow"):
        # --runslow given in cli: do not skip slow tests
        return
    skip_slow = pytest.mark.skip(reason="need --runslow option to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
