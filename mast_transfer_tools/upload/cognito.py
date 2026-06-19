import base64
from dataclasses import dataclass
import hashlib
import json
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import secrets
import urllib.parse
import threading
from typing import NotRequired, Required, TypedDict, cast, Any
import webbrowser


import boto3
import botocore
from botocore import UNSIGNED
from botocore.config import Config
from botocore.credentials import RefreshableCredentials
from botocore.exceptions import ClientError
import requests

from mast_transfer_tools.types import CognitoConfiguration


class CognitoTokens(TypedDict):
    """
    Stable token state kept in CognitoCredentialsManager.auth_result["tokens"].

    This should include refresh_token after the initial authorization-code
    exchange. Refresh responses may omit refresh_token, but the manager should
    preserve the existing one.
    """

    id_token: str
    access_token: str
    refresh_token: str
    expires_in: NotRequired[int]
    token_type: NotRequired[str]
    scope: NotRequired[str]


class CognitoTokenRefreshResponse(TypedDict, total=False):
    """
    Raw response from Cognito refresh_token grant.

    Cognito may return only new id/access tokens. If refresh-token rotation is
    enabled, it may also return a new refresh_token.
    """

    id_token: str
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str
    scope: str


JwtPayload = TypedDict(
    "JwtPayload",
    {
        "sub": str,
        "aud": str,
        "iss": str,
        "token_use": str,
        "auth_time": int,
        "iat": int,
        "exp": int,
        "email": str,
        "email_verified": bool,
        "cognito:username": str,
        "cognito:groups": list[str],
        "cognito:roles": list[str],
        "cognito:preferred_role": str,
    },
    total=False,
)
"""
Decoded JWT payload. (Functional syntax is needed for keys containing ':').
"""


class AWSCredentials(TypedDict):
    """
    Normalized credentials exposed by manager.
    """

    access_key_id: str
    secret_access_key: str
    session_token: str
    expiration: str


class IdentityPoolCredentials(TypedDict):
    """
    Raw Credentials member from get_credentials_for_identity.
    """

    AccessKeyId: str
    SecretKey: str
    SessionToken: str
    Expiration: datetime


class IdentityPoolCredentialsResponse(TypedDict):
    """
    Raw response from Cognito Identity get_credentials_for_identity.
    """

    IdentityId: str
    Credentials: IdentityPoolCredentials


class RefreshableCredentialMetadata(TypedDict):
    """
    Shape required by botocore.credentials.RefreshableCredentials.
    Yes, the key names are different from boto3 default.
    """

    access_key: str
    secret_key: str
    token: str
    expiry_time: str


class TokenRequestBody(TypedDict, total=False):
    grant_type: Required[str]
    client_id: str
    code: str
    code_verifier: str
    redirect_uri: str
    refresh_token: str


@dataclass
class OAuthCallbackResult:
    authorization_code: str | None = None
    error: str | None = None
    error_description: str | None = None
    state: str | None = None


class OAuthCallbackServer(HTTPServer):
    def __init__(
        self,
        server_address: (
            tuple[str | bytes | bytearray, int]
            | tuple[str | bytes | bytearray, int, int, int]
        ),
        handler_class: Any,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.result = OAuthCallbackResult()


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP request handler for OAuth callback"""

    server: OAuthCallbackServer

    def do_GET(self) -> None:
        parsed_path = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed_path.query)
        self.server.result.state = params.get("state", [None])[0]

        has_code = "code" in params
        has_error = "error" in params

        if has_code == has_error:
            # either both present or neither present
            self.server.result.error = "invalid_callback"
            self.server.result.error_description = (
                f"unexpected response: {params}"
            )
            self.send_error(400, "Invalid OAuth callback")
            return

        if has_code:
            self.server.result.authorization_code = params["code"][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                b"Authorization complete. You can close this window."
            )
            return

        self.server.result.error = params["error"][0]
        self.server.result.error_description = params.get(
            "error_description",
            ["Unknown error"],
        )[0]
        self.send_response(400)
        self.end_headers()
        self.wfile.write(b"Authorization failed. You can close this window.")

    def log_message(self, fmt: Any, *args: Any) -> None:
        pass


class CognitoOAuthAuthenticator:
    """Handles AWS Cognito OAuth authentication with PKCE"""

    def __init__(
        self,
        cognito_domain: str,
        client_id: str,
        redirect_uri: str = "http://localhost:3000",
        region: str = "us-east-1",
    ) -> None:
        """
        Initialize the Cognito OAuth authenticator

        Args:
            cognito_domain: Your Cognito domain (e.g., 'your-app.auth.us-east-1.amazoncognito.com')
            client_id: The App Client ID from Cognito
            redirect_uri: The redirect URI configured in your Cognito app client
            region: AWS region where your Cognito user pool is located
        """
        self.cognito_domain = cognito_domain
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.region = region

        self.authorization_endpoint = (
            f"https://{cognito_domain}/oauth2/authorize"
        )
        self.token_endpoint = f"https://{cognito_domain}/oauth2/token"

    @staticmethod
    def generate_pkce_pair() -> tuple[str, str]:
        """
        Generate PKCE code verifier and challenge

        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        code_verifier = base64.urlsafe_b64encode(
            secrets.token_bytes(32)
        ).decode("utf-8")
        code_verifier = code_verifier.rstrip("=")

        code_challenge = hashlib.sha256(code_verifier.encode("utf-8")).digest()
        code_challenge = base64.urlsafe_b64encode(code_challenge).decode(
            "utf-8"
        )
        code_challenge = code_challenge.rstrip("=")

        return code_verifier, code_challenge

    def start_local_server(self, port: int = 3000) -> OAuthCallbackServer:
        """
        Start a local HTTP server to receive the OAuth callback

        Args:
            port: Port number to listen on

        Returns:
            HTTPServer instance

        Raises:
            ConnectionError: if HTTPServer cannot connect to port

        Security Notes:
            - Uses localhost only (no network exposure)
            - Port must match the callback URL configured in Cognito
            - Cannot use alternate ports without updating Cognito settings
        """
        try:
            return OAuthCallbackServer(
                ("127.0.0.1", port), OAuthCallbackHandler
            )
        except OSError as e:
            # Address already in use (macOS/Linux)
            if e.errno == 48 or e.errno == 98:
                raise ConnectionError(
                    f"\n❌ Port {port} is already in use.\n\n"
                    f"To fix this:\n"
                    f"Note: The port number must match your Cognito Allowed "
                    f"Callback URL configuration.\n"
                    f"      Current callback URL: {self.redirect_uri}"
                ) from e
            raise ConnectionError(
                f"Failed to start local server on port {port}: {str(e)}"
            ) from e

    def get_authorization_url(self, code_challenge: str, state: str) -> str:
        """
        Build the authorization URL for the OAuth flow

        Args:
            code_challenge: PKCE code challenge
            state: Random state parameter for CSRF protection

        Returns:
            Authorization URL
        """
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
            "scope": "openid email",
        }

        return (
            f"{self.authorization_endpoint}?{urllib.parse.urlencode(params)}"
        )

    def _post_token_request(
        self,
        data: TokenRequestBody,
        failure_message: str,
    ) -> CognitoTokenRefreshResponse:
        """Helper for token-exchange / refresh workflows."""
        body = {
            "client_id": self.client_id,
            **data,
        }

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        response = requests.post(
            self.token_endpoint,
            data=body,
            headers=headers,
            auth=None,
            timeout=15,
        )

        if response.status_code != 200:
            raise PermissionError(f"{failure_message}: {response.text}")

        return response.json()

    def exchange_code_for_tokens(
        self, authorization_code: str, code_verifier: str
    ) -> CognitoTokens:
        """
        Exchange authorization code for access tokens

        Args:
            authorization_code: Authorization code from OAuth callback
            code_verifier: PKCE code verifier

        Returns:
            dict containing tokens (id_token, access_token, refresh_token)
        """
        data: TokenRequestBody = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "code_verifier": code_verifier,
            "redirect_uri": self.redirect_uri,
        }

        tokens = self._post_token_request(
            data,
            failure_message="Token exchange failed",
        )

        if "id_token" not in tokens:
            raise PermissionError("Token exchange response missing id_token")
        if "access_token" not in tokens:
            raise PermissionError(
                "Token exchange response missing access_token"
            )
        if "refresh_token" not in tokens:
            raise PermissionError(
                "Token exchange response missing refresh_token"
            )

        return cast(CognitoTokens, tokens)

    def refresh_tokens(
        self, refresh_token: str
    ) -> CognitoTokenRefreshResponse:
        """
        exchange a refresh token for fresh Cognito User Pool tokens.

        Usually returns new id_token/access_token.
        If refresh-token rotation is enabled, Cognito can also return a new
        refresh_token. Preserve the old one if Cognito does not return one.
        """
        data: TokenRequestBody = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        tokens = self._post_token_request(
            data,
            failure_message=(
                "Token refresh failed. The refresh token may be expired, "
                "revoked, rotated out, or rejected by the app client"
            ),
        )
        tokens.setdefault("refresh_token", refresh_token)
        return tokens

    def authenticate(self) -> CognitoTokens:
        """
        Perform the complete OAuth authentication flow

        Returns:
            dict containing authentication tokens and user info
        """

        code_verifier, code_challenge = self.generate_pkce_pair()
        state = secrets.token_urlsafe(32)

        port = int(self.redirect_uri.split(":")[-1].split("/")[0])
        server = self.start_local_server(port)

        server_thread = threading.Thread(target=server.handle_request)
        server_thread.daemon = True
        server_thread.start()

        auth_url = self.get_authorization_url(code_challenge, state)
        webbrowser.open(auth_url)
        server_thread.join(timeout=300)

        if server.result.error:
            raise ConnectionError(
                f"Authentication failed: {server.result.error}"
            )
        if not server.result.authorization_code:
            raise ConnectionError("Authentication cancelled or timed out")

        if server.result.state != state:
            raise PermissionError(
                "Authentication failed: OAuth state mismatch "
                "(possible CSRF attempt)"
            )

        return self.exchange_code_for_tokens(
            server.result.authorization_code, code_verifier
        )


def _now() -> datetime:
    """now, as a UTC datetime"""
    return datetime.now(timezone.utc)


def _jwt_expiration(jwt_token: str) -> datetime:
    """Expiration time of this token, as a UTC datetime"""
    claims = decode_jwt_payload(jwt_token)
    return datetime.fromtimestamp(int(claims["exp"]), tz=timezone.utc)


def _require_aware_utc(dt: datetime, name: str) -> datetime:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(
            f"{name} is timezone-naive: {dt!r}. "
            "Refusing to guess whether this means UTC or local time."
        )

    return dt.astimezone(timezone.utc)


class CognitoCredentialsManager:
    """
    Manages AWS credentials using Cognito Identity Pool.

    Intended long-running usage:
        manager = get_authenticated_cognito_manager(cogconf)
        session = manager.make_refreshing_session(role_suffix="SomeRole")
        s3 = session.client("s3")

    Worker threads should use clients created from the returned session.
    They should not call refresh methods directly.
    """

    def __init__(
        self,
        identity_pool_id: str,
        user_pool_id: str,
        region: str = "us-east-1",
        auth_tokens: CognitoTokens | None = None,
        authenticator: CognitoOAuthAuthenticator | None = None,
    ) -> None:
        """
        Args:
            identity_pool_id: Cognito Identity Pool ID
            user_pool_id: Cognito User Pool ID
            region: AWS region
            auth_tokens: prefetched tokens
                [optional, can be fetched later]
            authenticator: preconstructed authenticator
                [optional, can be provided later]
        """
        self.auth_tokens = auth_tokens
        self.authenticator = authenticator
        self.identity_pool_id = identity_pool_id
        self.user_pool_id = user_pool_id
        self.region = region

        self.identity_id: str | None = None
        self.credentials: AWSCredentials | None = None
        self.creds_response: IdentityPoolCredentialsResponse | None = None

        self.last_role_suffix: str | None = None

        # botocore protects its own RefreshableCredentials object, but
        # we need our own lock to protect the mutable manager state.
        self._refresh_lock = threading.RLock()

    @property
    def _logins_key(self) -> str:
        return f"cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"

    def _id_token_expiring(
        self,
        margin: timedelta = timedelta(minutes=5),
    ) -> bool:
        """
        Is our id token less than `margin` from expiration (or already
        expired)? Also True if token has never been fetched.
        """
        if self.auth_tokens is None:
            return True

        id_token = self.auth_tokens["id_token"]
        return _jwt_expiration(id_token) <= _now() + margin

    def _aws_credentials_expiring(
        self,
        margin: timedelta = timedelta(minutes=5),
    ) -> bool:
        """
        Are our AWS credentials less than `margin` from expiration (or already
        expired)? Also True if credentials have never been fetched.
        """

        if self.creds_response is None or self.credentials is None:
            return True

        expiration = _require_aware_utc(
            self.creds_response["Credentials"]["Expiration"],
            "Cognito Identity credentials expiration",
        )

        return expiration <= _now() + margin

    @staticmethod
    def _select_role(id_token: str, role_suffix: str | None) -> str:
        """
        Select a role matching role_suffix, if any. Raise an exception if
        role_suffix is provided and there is not exactly one matching role.
        If role_suffix is not provided, return the "first" available role, or
        throw if there are none available.
        """
        claims = decode_jwt_payload(id_token)
        roles = claims.get("cognito:roles", [])

        if len(roles) == 0:
            raise PermissionError("No roles are associated with this identity")

        if role_suffix is None:
            return roles[0]

        matches = [r for r in roles if r.endswith(role_suffix)]

        if len(matches) == 0:
            raise PermissionError(
                f"No available roles match {role_suffix}. Available roles "
                f"are {roles}. If this is incorrect, please contact your "
                f"system administrator."
            )

        if len(matches) > 1:
            raise PermissionError(
                f"Too many roles matching {role_suffix}. Matching roles "
                f"are {matches}. If this is incorrect, please contact "
                f"your system administrator."
            )

        return matches[0]

    def refresh_user_pool_tokens(self) -> CognitoTokens:
        """
        Refresh Cognito User Pool ID/access tokens using previously-retrieved
        refresh token.
        """
        with self._refresh_lock:
            if self.authenticator is None:
                raise ConnectionError(
                    "Cannot refresh tokens: no CognitoOAuthAuthenticator "
                    "is attached."
                )

            if self.auth_tokens is None:
                raise ConnectionError(
                    "Cannot refresh tokens: no auth_result is available."
                )

            refresh_token = self.auth_tokens.get("refresh_token")
            if not refresh_token:
                raise PermissionError(
                    "Cannot refresh tokens: auth_result has no refresh_token."
                )

            new_tokens = self.authenticator.refresh_tokens(refresh_token)
            self.auth_tokens.update(new_tokens)

            return self.auth_tokens

    def get_credentials(
        self, id_token: str | None = None, role_suffix: str | None = None
    ) -> AWSCredentials:
        """
        Exchange Cognito ID token for AWS credentials using Identity Pool.
        Updates self.creds_response and self.credentials.

        Args:
            id_token: ID token from Cognito authentication. if not provided,
                uses id_token from self.auth_result if available
            role_suffix: if provided, checks available roles and
                requests credentials for the role with that string suffix.
                If there is not exactly one available role with that suffix,
                raises a PermissionError. If not provided, returns the first
                available role (if any).

        Returns:
            self.credentials (dictionary containing AWS credentials)
        """
        with self._refresh_lock:
            if id_token is None and self.auth_tokens is None:
                raise PermissionError(
                    "Must provide id_token if no auth_result is available"
                )

            if id_token is None:
                id_token = self.auth_tokens["id_token"]

            if role_suffix is not None:
                self.last_role_suffix = role_suffix
            else:
                role_suffix = self.last_role_suffix

            role = self._select_role(id_token, role_suffix)

            cog_client = boto3.client(
                "cognito-identity",
                region_name=self.region,
                config=Config(signature_version=UNSIGNED),
            )

            try:
                identity_response = cog_client.get_id(
                    IdentityPoolId=self.identity_pool_id,
                    Logins={self._logins_key: id_token},
                )
                self.creds_response = cog_client.get_credentials_for_identity(
                    IdentityId=identity_response["IdentityId"],
                    Logins={self._logins_key: id_token},
                    CustomRoleArn=role,
                )
                creds = self.creds_response["Credentials"]
                self.credentials = {
                    "access_key_id": creds["AccessKeyId"],
                    "secret_access_key": creds["SecretKey"],
                    "session_token": creds["SessionToken"],
                    "expiration": creds["Expiration"].isoformat(),
                }
            except ClientError as e:
                raise ConnectionError("Failed to get AWS credentials") from e

            return self.credentials

    def ensure_credentials(
        self,
        role_suffix: str | None = None,
        refresh_margin: timedelta = timedelta(minutes=5),
    ) -> AWSCredentials:
        """
        Ensure both layers are fresh enough:

        1. Cognito User Pool ID/access tokens.
        2. Cognito Identity Pool AWS credentials.
        """
        with self._refresh_lock:
            if role_suffix is not None:
                self.last_role_suffix = role_suffix
            else:
                role_suffix = self.last_role_suffix

            if self._id_token_expiring(refresh_margin):
                self.refresh_user_pool_tokens()

            if self._aws_credentials_expiring(refresh_margin):
                return self.get_credentials(role_suffix=role_suffix)

            return self.credentials

    def _refreshable_metadata(
        self,
        role_suffix: str | None = None,
    ) -> RefreshableCredentialMetadata:
        """
        Return credentials in the exact shape botocore RefreshableCredentials
        expects.
        """
        with self._refresh_lock:
            self.ensure_credentials(
                role_suffix=role_suffix,
                refresh_margin=timedelta(minutes=10),
            )

            if self.credentials is None or self.creds_response is None:
                raise ConnectionError(
                    "Credential refresh produced no credentials"
                )

            expiration = self.creds_response["Credentials"]["Expiration"]

            return {
                "access_key": self.credentials["access_key_id"],
                "secret_key": self.credentials["secret_access_key"],
                "token": self.credentials["session_token"],
                "expiry_time": expiration.isoformat(),
            }

    def make_refreshing_session(
        self,
        role_suffix: str | None = None,
    ) -> boto3.Session:
        """
        Create a boto3 Session backed by botocore refreshable credentials.

        Prefer this method to make_session() for long-running workloads.
        """
        refreshable_credentials = RefreshableCredentials.create_from_metadata(
            metadata=self._refreshable_metadata(role_suffix),
            refresh_using=lambda: self._refreshable_metadata(role_suffix),
            method="cognito-identity",
            advisory_timeout=15 * 60,
            mandatory_timeout=10 * 60,
        )
        botocore_session = botocore.session.get_session()
        botocore_session._credentials = refreshable_credentials
        botocore_session.set_config_variable("region", self.region)

        return boto3.Session(botocore_session=botocore_session)

    def make_session(self, role_suffix: str | None = None) -> boto3.Session:
        """
        Create a normal static boto3 Session. Use for short-lived operations.
        For longer-running workloads, prefer make_refreshable_session().\
        """
        self.ensure_credentials(role_suffix=role_suffix)
        return boto3.Session(
            aws_access_key_id=self.credentials["access_key_id"],
            aws_secret_access_key=self.credentials["secret_access_key"],
            aws_session_token=self.credentials["session_token"],
            region_name=self.region,
        )


def decode_jwt_payload(jwt_token: str) -> JwtPayload:
    parts = jwt_token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT format")
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    decoded = base64.urlsafe_b64decode(payload + padding)
    return json.loads(decoded.decode("utf-8"))


def get_authenticated_cognito_manager(
    cogconf: CognitoConfiguration,
) -> CognitoCredentialsManager:
    authenticator = CognitoOAuthAuthenticator(
        cognito_domain=cogconf.domain,
        client_id=cogconf.client_id,
        redirect_uri=cogconf.redirect_uri,
        region=cogconf.region,
    )
    auth_tokens = authenticator.authenticate()
    return CognitoCredentialsManager(
        cogconf.identity_pool_id,
        cogconf.user_pool_id,
        region=cogconf.region,
        auth_tokens=auth_tokens,
        authenticator=authenticator,
    )
