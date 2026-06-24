import argparse
import json
import os
import sys

from globus_sdk import (
    AuthAPIError,
    AuthClient,
    NativeAppAuthClient,
    RefreshTokenAuthorizer,
)
from globus_sdk.scopes import AuthScopes
from globus_sdk.token_storage import JSONTokenStorage


globus_client_id = "4950867e-8eb0-49db-9573-840056513340"
view_my_groups_and_memberships_scope_uuid = "73320ffe-4cb4-4b25-a0a3-83d53d59ce4f"


project_name = "ESGFNG"


class WestDeployment:
    def __init__(self):
        self.native_client = NativeAppAuthClient(client_id=globus_client_id, app_name="West Deployment Client")
        self.scopes = [AuthScopes.manage_projects, "openid", "profile", "email"]
        filename = os.path.expanduser("~/.deployment_tokens.json")
        self.token_storage = JSONTokenStorage(filename)

    def do_login_flow(self):
        self.native_client.oauth2_start_flow(requested_scopes=self.scopes, refresh_tokens=True)
        authorize_url = self.native_client.oauth2_get_authorize_url(prompt="login")
        print("Please go to this URL and login: {0}".format(authorize_url))
        auth_code = input("Please enter the code here: ").strip()
        return self.native_client.oauth2_exchange_code_for_tokens(auth_code)

    def get_tokens(self, resource_server, prompt=None):
        if not self.token_storage.file_exists() or prompt:
            response = self.do_login_flow()
            self.token_storage.store_token_response(response)
        tokens = self.token_storage.get_token_data(resource_server)
        return tokens

    def get_auth_client(self, prompt=None):
        tokens = self.get_tokens(AuthClient.resource_server, prompt)
        auth_authorizer = RefreshTokenAuthorizer(
            tokens.refresh_token,
            self.native_client,
            access_token=tokens.access_token,
            expires_at=tokens.expires_at_seconds,
            on_refresh=self.token_storage.store_token_response,
        )
        auth_client = AuthClient(authorizer=auth_authorizer)
        return auth_client

    def get_user_info(self):
        r = self.auth_client.userinfo()
        self.sub = r.data.get("sub")
        self.email = r.data.get("email")
        print(f"sub: {self.sub}, email: {self.email}")

    def get_project(self):
        r = self.auth_client.get_projects()
        print(json.dumps(r.data, indent=4))
        project_id = None
        for project in r.data.get("projects", []):
            _project_name = project.get("project_name", "")
            _display_name = project.get("display_name", "")
            if _project_name != project_name or _display_name != project_name:
                continue
            admin_identities = project.get("admins", []).get("identities", [])
            for identity in admin_identities:
                if identity.get("id") == self.sub:
                    project_id = project.get("id")
                    break
            if project_id:
                break

        if not project_id:
            r = self.auth_client.create_project(project_name, self.email, admin_ids=[self.sub])
            project_id = r.data.get("project", {}).get("id")
        self.project_id = project_id
        print(f"project_id: {self.project_id}")

    def get_client(self, new_client_name):
        r = self.auth_client.get_clients()
        for client in r.data.get("clients", []):
            project_id = client.get("project", "")
            if project_id != self.project_id:
                continue
            name = client.get("name", "")
            if name != new_client_name:
                continue
            print(json.dumps(client, indent=4))
            print(f"Error: client '{new_client_name}' already exists")
            sys.exit(1)

    def create_client(self, new_client_name):
        r = self.auth_client.create_client(new_client_name, self.project_id, client_type="resource_server")

        self.service_client_id = r.data.get("client").get("id")
        r = self.auth_client.create_client_credential(self.service_client_id, "STAC Transaction API Service Client")
        print(json.dumps(r.data, indent=4))
        self.service_client_secret = r.data.get("credential").get("secret")

    def get_dependent_scope(self):
        r = self.auth_client.create_scope(
            self.service_client_id,
            "ESGF West STAC Transaction API",
            "Read ESGF publisher group membership",
            "transaction",
            dependent_scopes=[
                {
                    "scope": view_my_groups_and_memberships_scope_uuid,
                    "optional": False,
                    "requires_refresh_token": True,
                }
            ],
            advertised=True,
        )
        print(json.dumps(r.data, indent=4))

    def setup_service_client(self, name_suffix):
        self.auth_client = self.get_auth_client()
        self.get_user_info()
        self.get_project()
        new_client_name = f"ESGF West Transaction API Service Client {name_suffix}"
        self.get_client(new_client_name)
        try:
            self.create_client(new_client_name)
        except AuthAPIError:
            self.auth_client = self.get_auth_client(prompt="login")
            self.create_client(new_client_name)

        self.get_dependent_scope()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--client-name-suffix",
        required=True,
        help="suffix that will be added to the client name 'ESGF West STAC Transaction API Service Client '",
    )
    args = parser.parse_args()

    wd = WestDeployment()
    wd.setup_service_client(args.client_name_suffix)
