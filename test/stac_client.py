import os

from globus_sdk import (
    BaseClient,
    GroupsClient,
    NativeAppAuthClient,
    RefreshTokenAuthorizer,
)
from globus_sdk.scopes import GroupsScopes
from globus_sdk.tokenstorage import SimpleJSONFileAdapter

from settings import STAC_CLIENT, STAC_TRANSACTION_API, TOKEN_STORAGE_FILE

__version__ = "0.2.0"


class TransactionClient:
    def __init__(self, stac_api=None, verbose=False, silent=False):
        if stac_api:
            self.stac_api = stac_api
        else:
            self.stac_api = STAC_TRANSACTION_API.get("base_url")
        self.scopes = [
            GroupsScopes.view_my_groups_and_memberships,
            STAC_TRANSACTION_API.get("scope_string"),
        ]
        self.auth_client = NativeAppAuthClient(
            client_id=STAC_CLIENT.get("client_id"),
            app_name="ESGF2 STAC Transaction API",
        )
        self._create_clients()

    def _do_login_flow(self):
        self.auth_client.oauth2_start_flow(requested_scopes=self.scopes, refresh_tokens=True)
        authorize_url = self.auth_client.oauth2_get_authorize_url()
        print("Please go to this URL and login: {0}".format(authorize_url))
        auth_code = input("Please enter the code here: ").strip()
        return self.auth_client.oauth2_exchange_code_for_tokens(auth_code)

    def _create_clients(self):
        filename = os.path.expanduser(TOKEN_STORAGE_FILE)
        token_storage = SimpleJSONFileAdapter(filename)
        if not token_storage.file_exists():
            response = self._do_login_flow()
            token_storage.store(response)
            self.groups_tokens = response.by_resource_server[GroupsClient.resource_server]
            self.transaction_tokens = response.by_resource_server[STAC_TRANSACTION_API.get("client_id")]
        else:
            self.groups_tokens = token_storage.get_token_data(GroupsClient.resource_server)
            self.transaction_tokens = token_storage.get_token_data(STAC_TRANSACTION_API.get("client_id"))

        groups_authorizer = RefreshTokenAuthorizer(
            self.groups_tokens["refresh_token"],
            self.auth_client,
            access_token=self.groups_tokens["access_token"],
            expires_at=self.groups_tokens["expires_at_seconds"],
            on_refresh=token_storage.on_refresh,
        )
        self.groups_client = GroupsClient(authorizer=groups_authorizer)

        transaction_authorizer = RefreshTokenAuthorizer(
            self.transaction_tokens["refresh_token"],
            self.auth_client,
            access_token=self.transaction_tokens["access_token"],
            expires_at=self.transaction_tokens["expires_at_seconds"],
            on_refresh=token_storage.on_refresh,
        )
        self.transaction_client = BaseClient(base_url=self.stac_api, authorizer=transaction_authorizer)

    def get_my_groups(self):
        groups = self.groups_client.get_my_groups()
        return groups

    def post(self, entry):
        collection = entry.get("collection")
        headers = {
            "User-Agent": f"test_client/{__version__}",
        }
        resp = self.transaction_client.post(f"/collections/{collection}/items", headers=headers, data=entry)
        if resp.http_status == 201:
            print(resp.http_status)
            print("Published (POST)")
            return True
        elif resp.http_status == 202:
            print(resp.http_status)
            print("Queued for publication (POST)")
            return True
        else:
            print(f"Failed to publish (POST): Error {resp.http_status}")
            return False

    def put(self, entry):
        collection = entry.get("collection")
        item_id = entry.get("id")
        headers = {
            "User-Agent": f"test_client/{__version__}",
        }
        resp = self.transaction_client.put(f"/collections/{collection}/items/{item_id}", headers=headers, data=entry)
        if resp.http_status == 201:
            print(resp.http_status)
            print("Updated (PUT)")
            return True
        elif resp.http_status == 202:
            print(resp.http_status)
            print("Queued for update (PUT)")
            return True
        else:
            print(f"Failed to update (PUT): Error {resp.http_status}")
            return False

    def json_patch(self, collection, item_id, entry):
        """
        RFC 6902 https://tools.ietf.org/html/rfc6902
        JSON Patch is a format for describing changes to a JSON document
        in a way that is similar to a diff
        It consists of a sequence of operations to be applied to the target JSON document
        """
        headers = {
            "Content-Type": "application/json-patch+json",
            "User-Agent": f"test_client/{__version__}",
        }
        resp = self.transaction_client.patch(f"/collections/{collection}/items/{item_id}", headers=headers, data=entry)
        if resp.http_status == 201:
            print(resp.http_status)
            print("Updated (JSON PATCH)")
            return True
        elif resp.http_status == 202:
            print(resp.http_status)
            print("Queued for update (JSON PATCH)")
            return True
        else:
            print(f"Failed to update (JSON PATCH): Error {resp.http_status}")
            return False

    def merge_patch(self, collection, item_id, entry):
        """
        RFC 7396 https://tools.ietf.org/html/rfc7396
        Merge Patch is a format for describing changes to a JSON document
        that is intended to be applied in a way that is similar to a merge
        """
        headers = {
            "Content-Type": "application/merge-patch+json",
            "User-Agent": f"test_client/{__version__}",
        }
        resp = self.transaction_client.patch(f"/collections/{collection}/items/{item_id}", headers=headers, data=entry)
        if resp.http_status == 201:
            print(resp.http_status)
            print("Updated (MERGE PATCH)")
            return True
        elif resp.http_status == 202:
            print(resp.http_status)
            print("Queued for update (MERGE PATCH)")
            return True
        else:
            print(f"Failed to update (MERGE PATCH): Error {resp.http_status}")
            return False
