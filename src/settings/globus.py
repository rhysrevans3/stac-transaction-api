import json
from typing import Any, Self

import boto3
import urllib3
from globus_sdk import ConfidentialAppAuthClient
from pydantic import BaseModel, model_validator


class GlobusClientSettings(BaseModel):
    """
    Globus settings
    """

    client_id: str
    client_secret: str
    issuer: str
    scope_string: str

    access_control_policy: dict
    confidential_client: Any

    policy_path: str
    secret_name: str = "transaction-api/integration"
    region: str = "us-east-1"
    authorizer_cache_ttl_seconds: int = 300

    def load_access_control_policy(policy_path: str) -> dict:
        """load access control policy

        Args:
            data (dict): inital data

        Returns:
            dict: data with access control policy
        """
        parsed = urllib3.util.parse_url(policy_path)
        if parsed.scheme == "file":
            with open(parsed.path) as file:
                print("Access Control Policy loaded")
                return json.load(file)
        else:
            http = urllib3.PoolManager()
            response = http.request("GET", policy_path)
            if response.status == 200:
                print("Access Control Policy loaded")
                return json.loads(response.data.decode("utf-8"))

    def load_secrets(data: dict) -> dict:
        """load secrets from AWS

        Args:
            data (dict): inital data

        Returns:
            dict: data with secrets
        """
        try:
            session = boto3.session.Session()
            client = session.client("secretsmanager", region_name=data["region"])
            response = client.get_secret_value(SecretId=data["secret_name"])
            secrets = json.loads(response["SecretString"])
        except Exception as e:
            print(f"Error loading secrets: {e}")
            secrets = {}

        for key, value in secrets.items():
            data[key] = value

        return data

    @model_validator(mode="before")
    @classmethod
    def pre_load(self, data: dict) -> Self:
        """
        Load the access control policy, secrets, and confidential_client.
        """
        data["access_control_policy"] = self.load_access_control_policy(data["policy_path"])

        data["confidential_client"] = ConfidentialAppAuthClient(
            client_id=data["client_id"],
            client_secret=data["client_secret"],
        )

        return data
