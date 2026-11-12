from datetime import datetime
from os.path import join

from hdx.utilities.compare import assert_files_same
from hdx.utilities.downloader import Download
from hdx.utilities.path import temp_dir
from hdx.utilities.retriever import Retrieve

from hdx.scraper.standards.pipeline import Pipeline


class TestPipeline:
    def test_pipeline(
        self, configuration, get_all_hdx_datasets, fixtures_dir, input_dir, config_dir
    ):
        with (
            temp_dir(
                "TestStandards",
                delete_on_success=True,
                delete_on_failure=False,
            ) as tempdir,
            Download(user_agent="test") as downloader,
        ):
            retriever = Retrieve(
                downloader=downloader,
                fallback_dir=tempdir,
                saved_dir=input_dir,
                temp_dir=tempdir,
                save=False,
                use_saved=True,
            )
            pipeline = Pipeline(configuration, retriever, tempdir)
            datasets_to_check = pipeline.get_datasets()
            assert len(datasets_to_check) == 322

            data = pipeline.check_datasets(datasets_to_check)
            dataset = pipeline.generate_dataset(data, datetime(2026, 11, 12))
            dataset.update_from_yaml(path=join(config_dir, "hdx_dataset_static.yaml"))
            assert dataset == {
                "name": "pipeline-guidelines",
                "title": "HDX Internal: Scripted datasets and pipeline guidelines",
                "dataset_date": "[2026-11-12T00:00:00 TO 2026-11-12T00:00:00]",
                "groups": [{"name": "world"}],
                "tags": [
                    {
                        "name": "survey",
                        "vocabulary_id": "b891512e-9516-4bf5-962a-7a289772a2a1",
                    }
                ],
                "license_id": "cc-by",
                "methodology": "Registry",
                "dataset_source": "HDX",
                "package_creator": "HDX Data Systems Team",
                "private": True,
                "maintainer": "aa13de36-28c5-47a7-8d0b-6d7c754ba8c8",
                "owner_org": "hdx",
                "data_update_frequency": 7,
                "notes": "This dataset checks scripted datasets for potential issues. Each column corresponds to an aspect that does not conform to the pipeline guidelines.",
            }

            resources = dataset.get_resources()
            assert resources[0] == {
                "name": "dataset_issues.csv",
                "description": "CSV of datasets and potential issues",
                "format": "csv",
            }

            assert_files_same(
                join(fixtures_dir, "dataset_issues.csv"),
                join(tempdir, "dataset_issues.csv"),
            )
