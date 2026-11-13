#!/usr/bin/python
"""Standards scraper"""

import logging
import re
from datetime import datetime

import requests
from hdx.api.configuration import Configuration
from hdx.data.dataset import Dataset
from hdx.location.country import Country
from hdx.utilities.retriever import Retrieve
from slugify import slugify

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, configuration: Configuration, retriever: Retrieve, tempdir: str):
        self._configuration = configuration
        self._retriever = retriever
        self._tempdir = tempdir
        self._repos = {}

    @staticmethod
    def get_datasets() -> list[Dataset]:
        logger.info("Getting datasets")
        datasets = Dataset.get_all_datasets(fq="archived:false AND private:false")
        scripted_datasets = []
        for dataset in datasets:
            updated_by_script = dataset.get("updated_by_script")
            if not updated_by_script:
                continue
            scripted_datasets.append(dataset)
        return scripted_datasets

    def check_datasets(
        self, datasets_to_check: list[Dataset]
    ) -> (list[dict], list[dict]):
        logger.info("Checking datasets")
        checked_datasets = []
        checked_pipelines = {}
        for dataset in datasets_to_check:
            dataset_data = {
                "name": dataset["name"],
                "title": dataset["title"],
            }

            # Check if dataset is part of HDX pipeline
            updated_by_script = dataset["updated_by_script"]
            updated_by_script, owner, repo = self._get_repo(updated_by_script)
            dataset_data["Updated by script"] = updated_by_script
            dataset_data["Pipeline owner"] = owner
            dataset_data["GitHub repo"] = repo
            if updated_by_script not in checked_pipelines:
                checked_pipelines[updated_by_script] = {
                    "Updated by script": updated_by_script,
                    "Pipeline owner": owner,
                    "GitHub repo": repo,
                    "Number of datasets": 1,
                }
            else:
                checked_pipelines[updated_by_script]["Number of datasets"] += 1

            # Check update frequency
            update_frequency_issue = None
            update_frequency = dataset.get_expected_update_frequency()
            if not update_frequency:
                update_frequency_issue = "Missing"
            elif update_frequency in ["Live", "As needed"]:
                update_frequency_issue = update_frequency
            dataset_data["Update frequency is missing/As needed/Live"] = (
                update_frequency_issue
            )
            checked_pipelines[updated_by_script] = self._add_to_pipeline_dict(
                checked_pipelines[updated_by_script],
                "Update frequency is missing/As needed/Live",
                update_frequency_issue,
            )

            # Check dataset title for "data"
            title = dataset["title"]
            title_issue = None
            if re.search(r"\sdata(\s|$)", title, re.IGNORECASE):
                title_issue = "Y"
            dataset_data["Title contains word 'data'"] = title_issue
            checked_pipelines[updated_by_script] = self._add_to_pipeline_dict(
                checked_pipelines[updated_by_script],
                "Title contains word 'data'",
                title_issue,
            )

            # Check dataset title for dates or version numbers
            title_issue = None
            if re.search(r"\D(19|20)\d\d(\D|$)", title, re.IGNORECASE):
                title_issue = "Y"
            if re.search(r"\s(v(\s\d|\.\s\d|\d))|(version\s?\d)", title, re.IGNORECASE):
                title_issue = "Y"
            dataset_data["Title contains date or version number"] = title_issue
            checked_pipelines[updated_by_script] = self._add_to_pipeline_dict(
                checked_pipelines[updated_by_script],
                "Title contains date or version number",
                title_issue,
            )

            # Check dataset slug for country names instead of iso codes
            name = slugify(dataset["name"]).replace("-", " ")
            name_issue = None
            dataset_iso = dataset.get_location_iso3s()
            if len(dataset_iso) == 1 and dataset_iso[0].lower() not in name.split(" "):
                iso, _ = Country.get_iso3_country_code_fuzzy(name)
                if iso and iso == dataset_iso[0]:
                    name_issue = "Y"
            dataset_data["Name contains country name instead of iso3"] = name_issue
            checked_pipelines[updated_by_script] = self._add_to_pipeline_dict(
                checked_pipelines[updated_by_script],
                "Name contains country name instead of iso3",
                name_issue,
            )

            # Check resource file size <= 300 MB
            resources = dataset.get_resources()
            file_size_issue = None
            for resource in resources:
                size = resource.get("size")
                if size and size > 314572800:
                    file_size_issue = "Y"
            dataset_data["Resource file size greater than 300 MB"] = file_size_issue
            checked_pipelines[updated_by_script] = self._add_to_pipeline_dict(
                checked_pipelines[updated_by_script],
                "Resource file size greater than 300 MB",
                file_size_issue,
            )

            checked_datasets.append(dataset_data)
        checked_pipelines = list(checked_pipelines.values())
        return checked_datasets, checked_pipelines

    def generate_dataset(
        self, checked_datasets: list[dict], checked_pipelines: list[dict], now: datetime
    ) -> Dataset | None:
        logger.info("Generating dataset")
        dataset = Dataset(
            {
                "name": "pipeline-guidelines",
                "title": "HDX Internal: Scripted datasets and pipeline guidelines",
            }
        )

        dataset.set_time_period(now)
        dataset.add_other_location("world")
        dataset.add_tag("survey")

        dataset.generate_resource(
            folder=self._tempdir,
            filename="dataset_issues.csv",
            rows=checked_datasets,
            headers=list(checked_datasets[0].keys()),
            resourcedata={
                "name": "dataset_issues.csv",
                "description": "CSV of datasets and potential issues",
            },
            encoding="utf-8-sig",
        )

        dataset.generate_resource(
            folder=self._tempdir,
            filename="pipeline_issues.csv",
            rows=checked_pipelines,
            headers=list(checked_pipelines[0].keys()),
            resourcedata={
                "name": "pipeline_issues.csv",
                "description": "CSV of pipeline potential issues",
            },
            encoding="utf-8-sig",
        )

        return dataset

    def _get_repo(self, updated_by_script: str) -> (str, str, str):
        owner = "Unknown"
        repo = "Unknown"
        if (
            "hdx scraper" in updated_by_script.lower()
            or "hdxinternal" in updated_by_script.lower()
        ):
            owner = "HDX"
        parts = updated_by_script.split(" (")
        if len(parts) > 1:
            parts = parts[:-1]
        updated_by_script = " (".join(parts)
        if owner != "HDX":
            return updated_by_script, owner, repo
        parts = updated_by_script.split(": ")
        if len(parts) > 1:
            parts = parts[1:]
        script_name = ": ".join(parts)
        repo_name = self._configuration["repos"].get(
            script_name, slugify(f"hdx-scraper-{script_name}")
        )
        if repo_name in self._repos:
            repo = self._repos[repo_name]
            return updated_by_script, owner, repo
        url = f"{self._configuration['base_github']}/{repo_name}"
        response = requests.get(url, headers={"Accept": "application/vnd.github+json"})
        if response.status_code == 200:
            self._repos[repo_name] = url
            repo = url
        else:
            repo = "Unknown"
            self._repos[repo_name] = repo
        return updated_by_script, owner, repo

    @staticmethod
    def _add_to_pipeline_dict(pipeline_dict: dict, key: str, value: str | None) -> dict:
        new_value = pipeline_dict.get(key, 0)
        if value:
            new_value += 1
        pipeline_dict[key] = new_value
        return pipeline_dict
