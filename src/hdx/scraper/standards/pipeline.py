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

    def check_datasets(self, datasets_to_check: list[Dataset]) -> list[dict]:
        logger.info("Checking datasets")
        checked_data = []
        for dataset in datasets_to_check:
            dataset_data = {
                "name": dataset["name"],
                "title": dataset["title"],
            }

            # Check if dataset is part of HDX pipeline
            updated_by_script = dataset["updated_by_script"]
            owner = "Unknown"
            repo = "Unknown"
            if (
                "hdx scraper" in updated_by_script.lower()
                or "hdxinternal" in updated_by_script.lower()
            ):
                owner = "HDX"
                repo, updated_by_script = self._get_repo(updated_by_script)
            dataset_data["Updated by script"] = updated_by_script
            dataset_data["Pipeline owner"] = owner
            dataset_data["GitHub repo"] = repo

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

            # Check dataset title for "data"
            title = dataset["title"]
            title_issue = None
            if re.search(r"\sdata(\s|$)", title, re.IGNORECASE):
                title_issue = "Y"
            dataset_data["Title contains word 'date'"] = title_issue

            # Check dataset title for dates or version numbers
            title_issue = None
            if re.search(r"\D(19|20)\d\d(\D|$)", title, re.IGNORECASE):
                title_issue = "Y"
            if re.search(r"\s(v(\s\d|\.\s\d|\d))|(version\s?\d)", title, re.IGNORECASE):
                title_issue = "Y"
            dataset_data["Title contains date or version number"] = title_issue

            # Check dataset slug for country names instead of iso codes
            name = slugify(dataset["name"]).replace("-", " ")
            name_issue = None
            dataset_iso = dataset.get_location_iso3s()
            if len(dataset_iso) == 1 and dataset_iso[0].lower() not in name.split(" "):
                iso, _ = Country.get_iso3_country_code_fuzzy(name)
                if iso and iso == dataset_iso[0]:
                    name_issue = "Y"
            dataset_data["Name contains country name instead of iso3"] = name_issue

            # Check resource file size <= 300 MB
            resources = dataset.get_resources()
            file_size_issue = None
            for resource in resources:
                size = resource.get("size")
                if size and size > 314572800:
                    file_size_issue = "Y"
            dataset_data["Resource file size greater than 300 MB"] = file_size_issue

            checked_data.append(dataset_data)
        return checked_data

    def generate_dataset(self, data: list[dict], now: datetime) -> Dataset | None:
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
            rows=data,
            headers=list(data[0].keys()),
            resourcedata={
                "name": "dataset_issues.csv",
                "description": "CSV of datasets and potential issues",
            },
            encoding="utf-8-sig",
        )

        return dataset

    def _get_repo(self, updated_by_script: str) -> (str, str):
        parts = updated_by_script.split(" (")
        if len(parts) > 1:
            parts = parts[:-1]
        updated_by_script = " (".join(parts)
        parts = updated_by_script.split(": ")
        if len(parts) > 1:
            parts = parts[1:]
        script_name = ": ".join(parts)
        repo_name = self._configuration["repos"].get(
            script_name, slugify(f"hdx-scraper-{script_name}")
        )
        if repo_name in self._repos:
            repo = self._repos[repo_name]
            return repo, updated_by_script
        url = f"{self._configuration['base_github']}/{repo_name}"
        response = requests.get(url, headers={"Accept": "application/vnd.github+json"})
        if response.status_code == 200:
            self._repos[repo_name] = url
            repo = url
        else:
            repo = "Unknown"
            self._repos[repo_name] = repo
        return repo, updated_by_script
