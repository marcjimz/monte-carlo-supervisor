import json
import logging
import os
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)
GENIE_SPACES_API = "api/2.0/genie/spaces"


class GenieInputError(ValueError):
    """Raised when required Genie inputs are missing or invalid."""


class GenieApiError(RuntimeError):
    """Raised when a Genie API call fails."""


class GenieApiBase:
    def __init__(self, host: str, dbutils) -> None:
        self.host = host.rstrip("/")
        self.dbutils = dbutils
        self._session = self._create_session()

    def _get_token(self) -> str:
        return (
            self.dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
        )

    def _get_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_token()}"}

    def _create_session(
        self,
        retries: int = 3,
        backoff_factor: float = 1.0,
        status_forcelist: tuple = (500, 502, 503, 504),
    ) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(
            total=retries,
            read=retries,
            connect=retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PATCH"],
            raise_on_status=False,
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session


class ExportGenie(GenieApiBase):
    """
    Exports Genie spaces as JSON files.

    Args:
        host (str): Databricks Host URL.
        dbutils: Databricks dbutils object. Used to retrieve the API token.
        root_dir (str): The root directory where the exported JSON file will be saved.
        source_genie_space_id (str): The ID of the Genie space to export.
        genie_export_filename (str): The name of the exported JSON file.
    """

    def __init__(
        self,
        host: str,
        dbutils,
        root_dir: str,
        source_genie_space_id: str,
        genie_export_filename: str = "genie_export",
    ) -> None:
        super().__init__(host, dbutils)
        self.root_dir = root_dir
        self.source_genie_space_id = source_genie_space_id
        self.genie_export_filename = genie_export_filename

    def _write_path(self) -> str:
        return os.path.join(self.root_dir, f"{self.genie_export_filename}.json")

    def export(self) -> int:
        """Exports Genie spaces as JSON files to the specified `root_dir` and `genie_export_filename`."""
        if not self.source_genie_space_id:
            raise GenieInputError("source_genie_space_id is required")

        url = f"{self.host}/{GENIE_SPACES_API}/{self.source_genie_space_id}?include_serialized_space=true"
        response = self._session.get(url, headers=self._get_headers())

        if not response.ok:
            raise GenieApiError(
                f"Failed to export Genie Space {self.source_genie_space_id}: "
                f"{response.status_code} {response.text}"
            )

        json_data = response.json()
        file_path = self._write_path()
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            json.dump(json_data, f)

        logger.info("Exported space %s to %s", self.source_genie_space_id, file_path)
        return response.status_code


class ImportGenie(GenieApiBase):
    """
    Imports or updates Genie spaces from JSON exports.

    Args:
        host (str): Databricks Host URL.
        dbutils: Databricks dbutils object. Used to retrieve the API token.
        json_path (str): The path to the JSON file containing the Genie space export.
        target_genie_dir (str): The target directory for the imported Genie space.
        target_genie_space_id (str): The ID of the target Genie space.
        warehouse_id (str): The ID of the target warehouse for the imported Genie space.
    """

    def __init__(
        self,
        host: str,
        dbutils,
        json_path: str,
        target_genie_dir: Optional[str] = None,
        target_genie_space_id: Optional[str] = None,
        warehouse_id: Optional[str] = None,
    ) -> None:
        super().__init__(host, dbutils)
        self.json_path = json_path
        self.target_genie_dir = self._get_user_workspace(target_genie_dir)
        self.target_genie_space_id = target_genie_space_id
        self.warehouse_id = warehouse_id

    def _get_user_workspace(self, target_genie_dir: Optional[str]) -> str:
        if not target_genie_dir or not target_genie_dir.strip():
            username = (
                self.dbutils.notebook.entry_point.getDbutils()
                .notebook()
                .getContext()
                .userName()
                .get()
            )
            user_workspace_path = f"/Users/{username}"
            logger.info("No target genie dir specified. Using default: %s", user_workspace_path)
            return user_workspace_path
        return target_genie_dir

    def _validate_json_export(self, json_export: Dict[str, Any]) -> None:
        if "serialized_space" not in json_export:
            raise GenieInputError("JSON export missing required 'serialized_space' key")

    def update_genie(self, json_export: Dict[str, Any]) -> requests.Response:
        """Updates an existing Genie space."""
        self._validate_json_export(json_export)

        content = {
            "serialized_space": json_export["serialized_space"],
            "title": json_export.get("title", ""),
            "description": json_export.get("description", ""),
        }

        if not self.target_genie_space_id:
            raise GenieInputError("target_genie_space_id is required for update")

        url = f"{self.host}/{GENIE_SPACES_API}/{self.target_genie_space_id}"
        response = self._session.patch(url, headers=self._get_headers(), json=content)

        if not response.ok:
            raise GenieApiError(
                f"Failed to update Genie Space {self.target_genie_space_id}: "
                f"{response.status_code} {response.text}"
            )

        logger.info("Successfully updated Genie Space %s", self.target_genie_space_id)
        return response

    def create_genie(self, json_export: Dict[str, Any]) -> requests.Response:
        """Creates a new Genie space."""
        self._validate_json_export(json_export)

        if not self.warehouse_id:
            raise GenieInputError("warehouse_id is required for creating a new Genie")

        content = {
            "warehouse_id": self.warehouse_id,
            "parent_path": self.target_genie_dir,
            "serialized_space": json_export["serialized_space"],
            "title": json_export.get("title", ""),
            "description": json_export.get("description", ""),
        }

        url = f"{self.host}/{GENIE_SPACES_API}"
        response = self._session.post(url, headers=self._get_headers(), json=content)

        if not response.ok:
            raise GenieApiError(
                f"Failed to create a new Genie Space: {response.status_code} {response.text}"
            )

        r = response.json()
        logger.info("Successfully created a new Genie Space: %s", r.get("space_id"))
        logger.info("Genie URL: %s/genie/rooms/%s", self.host, r.get("space_id"))
        return response

    def import_or_update(self) -> int:
        """Imports or updates a Genie space from the JSON export."""
        try:
            with open(self.json_path) as f:
                json_export = json.load(f)
        except FileNotFoundError:
            raise GenieInputError(f"Export file not found: {self.json_path}")

        if not self.target_genie_space_id or str(self.target_genie_space_id).lower() == "none":
            response = self.create_genie(json_export)
        else:
            response = self.update_genie(json_export)

        return response.status_code
