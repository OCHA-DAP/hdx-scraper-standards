from os.path import join

import pytest
from hdx.api.configuration import Configuration
from hdx.api.locations import Locations
from hdx.data.dataset import Dataset
from hdx.data.vocabulary import Vocabulary
from hdx.location.country import Country
from hdx.utilities.loader import load_json
from hdx.utilities.useragent import UserAgent


@pytest.fixture(scope="session")
def fixtures_dir():
    return join("tests", "fixtures")


@pytest.fixture(scope="session")
def input_dir(fixtures_dir):
    return join(fixtures_dir, "input")


@pytest.fixture(scope="session")
def config_dir(fixtures_dir):
    return join("src", "hdx", "scraper", "standards", "config")


@pytest.fixture(scope="function")
def get_all_hdx_datasets(monkeypatch):
    def get_all_datasets(fq=None):
        datasets = []
        path = join("tests", "fixtures", "input", "all_datasets.json")
        jsonobj = load_json(path, loaderror_if_empty=False)
        for element in jsonobj:
            dataset = Dataset(element)
            dataset.separate_resources()
            datasets.append(dataset)
        return datasets

    monkeypatch.setattr(Dataset, "get_all_datasets", staticmethod(get_all_datasets))


@pytest.fixture(scope="session")
def configuration(config_dir):
    UserAgent.set_global("test")
    Configuration._create(
        hdx_read_only=True,
        hdx_site="prod",
        project_config_yaml=join(config_dir, "project_configuration.yaml"),
    )
    # Change locations below to match those needed in tests
    Locations.set_validlocations(
        [
            {"name": "world", "title": "World"},
        ]
    )
    Country.countriesdata(False)
    Vocabulary._approved_vocabulary = {
        "tags": [
            {"name": tag}
            # Change tags below to match those needed in tests
            for tag in ("survey",)
        ],
        "id": "b891512e-9516-4bf5-962a-7a289772a2a1",
        "name": "approved",
    }
    return Configuration.read()
