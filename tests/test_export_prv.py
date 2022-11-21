import glob
import os
import tempfile
import types

import pytest

import atmoswing_vigicrues as asv

DIR_PATH = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture
def options():
    with tempfile.TemporaryDirectory() as tmp_dir:
        options_full = asv.Options(
            types.SimpleNamespace(
                config_file=DIR_PATH + '/files/config_export_prv.yaml'
            ))

        action_options = options_full.config['post_actions'][0]['with']
        action_options['output_dir'] = tmp_dir

    return action_options


@pytest.fixture
def metadata():
    metadata = {
        "forecast_date": "2022-10-01 00:00:00",
    }
    return metadata


def count_files_recursively(options):
    nb_files = sum([len(files) for r, d, files in os.walk(options['output_dir'])])
    return nb_files


@pytest.fixture
def forecast_files():
    return glob.glob(DIR_PATH + "/files/atmoswing-forecasts-v2.1/2022/10/01/*.nc")


def test_export_prv_runs(options, forecast_files, metadata):
    export = asv.ExportPrv(options)
    export.feed(forecast_files, metadata)
    export.run()
    assert count_files_recursively(options) == 21
