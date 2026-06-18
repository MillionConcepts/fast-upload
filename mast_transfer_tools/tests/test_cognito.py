"""Behavioral tests for Cognito-backed upload credentials."""

import base64
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import threading
from typing import Any

import pytest
from botocore.exceptions import ClientError

import mast_transfer_tools.upload.cognito as cognito_mod
from mast_transfer_tools.upload.cognito import (
    CognitoCredentialsManager,
    CognitoOAuthAuthenticator,
)


NOW = datetime.now(timezone.utc).replace(microsecond=0)
REGION = "us-east-1"
IDENTITY_POOL_ID = "us-east-1:identity-pool"
USER_POOL_ID = "us-east-1_userpool"
UPLOAD_ROLE = "arn:aws:iam::123456789012:role/ProjectUploadRole"
READ_ROLE = "arn:aws:iam::123456789012:role/ProjectReadRole"


def _b64_json(data: dict[str, Any]) -> str:
    encoded = base64.urlsafe_b64encode(
        json.dumps(data, separators=(",", ":")).encode("utf-8")
    )
    return encoded.decode("ascii").rstrip("=")


def make_jwt(
    *,
    exp: datetime,
    roles: Iterable[str] = (UPLOAD_ROLE, READ_ROLE),
    subject: str = "user-1",
) -> str:
    """Make an unsigned JWT good enough for decode_jwt_payload()."""
    return ".".join(
        (
            _b64_json({"alg": "none", "typ": "JWT"}),
            _b64_json(
                {
                    "sub": subject,
                    "aud": "client",
                    "iss": "issuer",
                    "token_use": "id",
                    "exp": int(exp.timestamp()),
                    "cognito:roles": list(roles),
                }
            ),
            "",
        )
    )


def make_tokens(
    *,
    exp: datetime,
    refresh_token: str = "refresh-1",
    id_label: str = "id-1",
    roles: Iterable[str] = (UPLOAD_ROLE, READ_ROLE),
) -> cognito_mod.CognitoTokens:
    return {
        "id_token": make_jwt(exp=exp, roles=roles, subject=id_label),
        "access_token": f"access-{id_label}",
        "refresh_token": refresh_token,
    }


def make_aws_response(
    *,
    generation: int,
    exp: datetime,
) -> cognito_mod.IdentityPoolCredentialsResponse:
    return {
        "IdentityId": f"identity-{generation}",
        "Credentials": {
            "AccessKeyId": f"AKIA{generation}",
            "SecretKey": f"secret-{generation}",
            "SessionToken": f"session-{generation}",
            "Expiration": exp,
        },
    }


@dataclass
class FakeClock:
    now: datetime = NOW


@dataclass
class FakeAuthenticator:
    responses: list[cognito_mod.CognitoTokenRefreshResponse]
    refreshed_with: list[str] = field(default_factory=list)
    refresh_started: threading.Event | None = None
    continue_refresh: threading.Event | None = None

    def refresh_tokens(
        self,
        refresh_token: str,
    ) -> cognito_mod.CognitoTokenRefreshResponse:
        self.refreshed_with.append(refresh_token)
        if self.refresh_started is not None:
            self.refresh_started.set()
        if self.continue_refresh is not None:
            self.continue_refresh.wait(timeout=2)
        if not self.responses:
            raise AssertionError("unexpected token refresh")
        return self.responses.pop(0)


@dataclass(frozen=True)
class GetIdCall:
    identity_pool_id: str
    logins: dict[str, str]


@dataclass(frozen=True)
class GetCredentialsCall:
    identity_id: str
    logins: dict[str, str]
    custom_role_arn: str


@dataclass
class FakeCognitoIdentityClient:
    responses: list[cognito_mod.IdentityPoolCredentialsResponse]
    get_id_calls: list[GetIdCall] = field(default_factory=list)
    get_credentials_calls: list[GetCredentialsCall] = field(
        default_factory=list
    )
    get_credentials_error: BaseException | None = None

    def get_id(
        self,
        *,
        IdentityPoolId: str,
        Logins: dict[str, str],
    ) -> dict[str, str]:
        self.get_id_calls.append(GetIdCall(IdentityPoolId, dict(Logins)))
        return {"IdentityId": f"identity-{len(self.get_id_calls)}"}

    def get_credentials_for_identity(
        self,
        *,
        IdentityId: str,
        Logins: dict[str, str],
        CustomRoleArn: str,
    ) -> cognito_mod.IdentityPoolCredentialsResponse:
        self.get_credentials_calls.append(
            GetCredentialsCall(
                IdentityId,
                dict(Logins),
                CustomRoleArn,
            )
        )
        if self.get_credentials_error is not None:
            raise self.get_credentials_error
        if not self.responses:
            raise AssertionError("unexpected AWS credential refresh")
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    fake_clock = FakeClock()
    monkeypatch.setattr(cognito_mod, "_now", lambda: fake_clock.now)
    return fake_clock


@pytest.fixture
def identity_client(
    monkeypatch: pytest.MonkeyPatch,
) -> FakeCognitoIdentityClient:
    client = FakeCognitoIdentityClient(
        responses=[
            make_aws_response(generation=1, exp=NOW + timedelta(hours=1)),
            make_aws_response(generation=2, exp=NOW + timedelta(hours=2)),
            make_aws_response(generation=3, exp=NOW + timedelta(hours=3)),
        ]
    )

    def fake_boto3_client(
        service_name: str,
        *,
        region_name: str,
        config: Any,
    ) -> FakeCognitoIdentityClient:
        assert service_name == "cognito-identity"
        assert region_name == REGION
        assert config.signature_version == cognito_mod.UNSIGNED
        return client

    monkeypatch.setattr(cognito_mod.boto3, "client", fake_boto3_client)
    return client


def make_manager(
    *,
    auth_tokens: cognito_mod.CognitoTokens | None = None,
    authenticator: FakeAuthenticator | None = None,
) -> CognitoCredentialsManager:
    return CognitoCredentialsManager(
        identity_pool_id=IDENTITY_POOL_ID,
        user_pool_id=USER_POOL_ID,
        region=REGION,
        auth_tokens=auth_tokens,
        authenticator=authenticator,
    )


def test_ensure_credentials_uses_cache_when_both_layers_are_fresh(
    identity_client: FakeCognitoIdentityClient,
) -> None:
    manager = make_manager(
        auth_tokens=make_tokens(exp=NOW + timedelta(hours=1)),
        authenticator=FakeAuthenticator(responses=[]),
    )
    cached_credentials: cognito_mod.AWSCredentials = {
        "access_key_id": "cached-access",
        "secret_access_key": "cached-secret",
        "session_token": "cached-session",
        "expiration": (NOW + timedelta(hours=1)).isoformat(),
    }
    manager.credentials = cached_credentials
    manager.creds_response = make_aws_response(
        generation=99,
        exp=NOW + timedelta(hours=1),
    )

    assert manager.ensure_credentials() is cached_credentials
    assert identity_client.get_credentials_calls == []


def test_ensure_credentials_refreshes_only_user_pool_tokens_when_id_token_expires(
    identity_client: FakeCognitoIdentityClient,
) -> None:
    refreshed_tokens = make_tokens(
        exp=NOW + timedelta(hours=1),
        refresh_token="refresh-1",
        id_label="id-2",
    )
    authenticator = FakeAuthenticator(responses=[refreshed_tokens])
    manager = make_manager(
        auth_tokens=make_tokens(
            exp=NOW + timedelta(minutes=1),
            refresh_token="refresh-1",
            id_label="id-1",
        ),
        authenticator=authenticator,
    )
    cached_credentials: cognito_mod.AWSCredentials = {
        "access_key_id": "cached-access",
        "secret_access_key": "cached-secret",
        "session_token": "cached-session",
        "expiration": (NOW + timedelta(hours=1)).isoformat(),
    }
    manager.credentials = cached_credentials
    manager.creds_response = make_aws_response(
        generation=99,
        exp=NOW + timedelta(hours=1),
    )

    assert manager.ensure_credentials() is cached_credentials
    assert authenticator.refreshed_with == ["refresh-1"]
    assert manager.auth_tokens == refreshed_tokens
    assert identity_client.get_credentials_calls == []


def test_ensure_credentials_refreshes_only_aws_credentials_when_aws_credentials_expire(
    identity_client: FakeCognitoIdentityClient,
) -> None:
    authenticator = FakeAuthenticator(responses=[])
    manager = make_manager(
        auth_tokens=make_tokens(
            exp=NOW + timedelta(hours=1),
            refresh_token="refresh-1",
            id_label="id-1",
        ),
        authenticator=authenticator,
    )
    manager.credentials = {
        "access_key_id": "stale-access",
        "secret_access_key": "stale-secret",
        "session_token": "stale-session",
        "expiration": (NOW + timedelta(minutes=1)).isoformat(),
    }
    manager.creds_response = make_aws_response(
        generation=99,
        exp=NOW + timedelta(minutes=1),
    )

    credentials = manager.ensure_credentials(role_suffix="UploadRole")

    assert credentials["access_key_id"] == "AKIA1"
    assert authenticator.refreshed_with == []
    assert len(identity_client.get_credentials_calls) == 1
    assert (
        identity_client.get_credentials_calls[0].custom_role_arn == UPLOAD_ROLE
    )


def test_ensure_credentials_refreshes_user_pool_before_fetching_aws_credentials(
    identity_client: FakeCognitoIdentityClient,
) -> None:
    refreshed_tokens = make_tokens(
        exp=NOW + timedelta(hours=1),
        refresh_token="refresh-rotated",
        id_label="id-2",
    )
    authenticator = FakeAuthenticator(responses=[refreshed_tokens])
    manager = make_manager(
        auth_tokens=make_tokens(
            exp=NOW + timedelta(minutes=1),
            refresh_token="refresh-1",
            id_label="id-1",
        ),
        authenticator=authenticator,
    )
    manager.credentials = {
        "access_key_id": "stale-access",
        "secret_access_key": "stale-secret",
        "session_token": "stale-session",
        "expiration": (NOW + timedelta(minutes=1)).isoformat(),
    }
    manager.creds_response = make_aws_response(
        generation=99,
        exp=NOW + timedelta(minutes=1),
    )

    credentials = manager.ensure_credentials(role_suffix="UploadRole")

    assert credentials["access_key_id"] == "AKIA1"
    assert authenticator.refreshed_with == ["refresh-1"]
    assert manager.auth_tokens == refreshed_tokens
    assert (
        identity_client.get_credentials_calls[0].logins[manager._logins_key]
        == refreshed_tokens["id_token"]
    )


def test_refresh_user_pool_tokens_preserves_refresh_token_when_cognito_omits_it(
    identity_client: FakeCognitoIdentityClient,
) -> None:
    new_id_token = make_jwt(
        exp=NOW + timedelta(hours=1),
        subject="id-2",
    )
    authenticator = FakeAuthenticator(
        responses=[
            {
                "id_token": new_id_token,
                "access_token": "access-2",
            }
        ]
    )
    manager = make_manager(
        auth_tokens=make_tokens(
            exp=NOW + timedelta(minutes=1),
            refresh_token="refresh-1",
        ),
        authenticator=authenticator,
    )

    tokens = manager.refresh_user_pool_tokens()

    assert tokens["id_token"] == new_id_token
    assert tokens["access_token"] == "access-2"
    assert tokens["refresh_token"] == "refresh-1"
    assert identity_client.get_credentials_calls == []


def test_rotated_refresh_token_is_used_on_next_refresh() -> None:
    authenticator = FakeAuthenticator(
        responses=[
            make_tokens(
                exp=NOW + timedelta(minutes=1),
                refresh_token="refresh-2",
                id_label="id-2",
            ),
            make_tokens(
                exp=NOW + timedelta(hours=1),
                refresh_token="refresh-3",
                id_label="id-3",
            ),
        ]
    )
    manager = make_manager(
        auth_tokens=make_tokens(
            exp=NOW + timedelta(minutes=1),
            refresh_token="refresh-1",
            id_label="id-1",
        ),
        authenticator=authenticator,
    )

    manager.refresh_user_pool_tokens()
    manager.refresh_user_pool_tokens()

    assert authenticator.refreshed_with == ["refresh-1", "refresh-2"]
    assert manager.auth_tokens is not None
    assert manager.auth_tokens["refresh_token"] == "refresh-3"


def test_role_suffix_is_remembered_for_later_credential_refresh(
    identity_client: FakeCognitoIdentityClient,
) -> None:
    manager = make_manager(
        auth_tokens=make_tokens(exp=NOW + timedelta(hours=1)),
        authenticator=FakeAuthenticator(responses=[]),
    )

    first = manager.ensure_credentials(role_suffix="UploadRole")
    manager.creds_response = make_aws_response(
        generation=99,
        exp=NOW + timedelta(minutes=1),
    )
    second = manager.ensure_credentials()

    assert first["access_key_id"] == "AKIA1"
    assert second["access_key_id"] == "AKIA2"
    assert [
        call.custom_role_arn for call in identity_client.get_credentials_calls
    ] == [UPLOAD_ROLE, UPLOAD_ROLE]


def test_ambiguous_role_suffix_fails_before_any_aws_call(
    identity_client: FakeCognitoIdentityClient,
) -> None:
    manager = make_manager(
        auth_tokens=make_tokens(
            exp=NOW + timedelta(hours=1),
            roles=[
                "arn:aws:iam::123456789012:role/TeamUploadRole",
                "arn:aws:iam::123456789012:role/AdminUploadRole",
            ],
        ),
        authenticator=FakeAuthenticator(responses=[]),
    )

    with pytest.raises(PermissionError, match="Too many roles"):
        manager.ensure_credentials(role_suffix="UploadRole")

    assert identity_client.get_credentials_calls == []


def test_botocore_refresh_callback_keeps_role_and_refreshes_expired_layers(
    identity_client: FakeCognitoIdentityClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity_client.responses = [
        make_aws_response(generation=1, exp=NOW + timedelta(minutes=11)),
        make_aws_response(generation=2, exp=NOW + timedelta(hours=2)),
    ]
    authenticator = FakeAuthenticator(
        responses=[
            make_tokens(
                exp=NOW + timedelta(hours=2),
                refresh_token="refresh-2",
                id_label="id-2",
            )
        ]
    )
    manager = make_manager(
        auth_tokens=make_tokens(
            exp=NOW + timedelta(hours=1),
            refresh_token="refresh-1",
            id_label="id-1",
        ),
        authenticator=authenticator,
    )

    session = manager.make_refreshing_session(role_suffix="UploadRole")
    clock_time_after_first_fetch = NOW + timedelta(hours=1, minutes=55)
    monkeypatch.setattr(
        cognito_mod,
        "_now",
        lambda: clock_time_after_first_fetch,
    )
    session._session.get_credentials()._refresh()

    assert authenticator.refreshed_with == ["refresh-1"]
    assert [
        call.custom_role_arn for call in identity_client.get_credentials_calls
    ] == [UPLOAD_ROLE, UPLOAD_ROLE]
    assert (
        identity_client.get_credentials_calls[-1].logins[manager._logins_key]
        == manager.auth_tokens["id_token"]
    )


def test_concurrent_ensure_credentials_collapses_refresh_storm(
    identity_client: FakeCognitoIdentityClient,
) -> None:
    refresh_started = threading.Event()
    continue_refresh = threading.Event()
    authenticator = FakeAuthenticator(
        responses=[
            make_tokens(
                exp=NOW + timedelta(hours=1),
                refresh_token="refresh-2",
                id_label="id-2",
            )
        ],
        refresh_started=refresh_started,
        continue_refresh=continue_refresh,
    )
    manager = make_manager(
        auth_tokens=make_tokens(
            exp=NOW + timedelta(minutes=1),
            refresh_token="refresh-1",
            id_label="id-1",
        ),
        authenticator=authenticator,
    )

    results: list[cognito_mod.AWSCredentials] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            results.append(
                manager.ensure_credentials(role_suffix="UploadRole")
            )
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for thread in threads:
        thread.start()

    assert refresh_started.wait(timeout=2)
    continue_refresh.set()
    for thread in threads:
        thread.join(timeout=2)

    assert errors == []
    assert len(results) == 10
    assert {result["access_key_id"] for result in results} == {"AKIA1"}
    assert authenticator.refreshed_with == ["refresh-1"]
    assert len(identity_client.get_credentials_calls) == 1


@pytest.mark.parametrize(
    ("seconds_after_margin", "should_refresh"),
    [
        (-1, True),
        (0, True),
        (1, False),
    ],
)
def test_expiration_exactly_at_refresh_margin_counts_as_expiring(
    identity_client: FakeCognitoIdentityClient,
    seconds_after_margin: int,
    *,
    should_refresh: bool,
) -> None:
    margin = timedelta(minutes=5)
    authenticator = FakeAuthenticator(
        responses=[
            make_tokens(
                exp=NOW + timedelta(hours=1),
                refresh_token="refresh-2",
                id_label="id-2",
            )
        ]
    )
    manager = make_manager(
        auth_tokens=make_tokens(
            exp=NOW + margin + timedelta(seconds=seconds_after_margin),
            refresh_token="refresh-1",
        ),
        authenticator=authenticator,
    )
    manager.credentials = {
        "access_key_id": "cached-access",
        "secret_access_key": "cached-secret",
        "session_token": "cached-session",
        "expiration": (NOW + timedelta(hours=1)).isoformat(),
    }
    manager.creds_response = make_aws_response(
        generation=99,
        exp=NOW + timedelta(hours=1),
    )

    manager.ensure_credentials(refresh_margin=margin)

    assert bool(authenticator.refreshed_with) is should_refresh


def test_failed_aws_credential_refresh_does_not_replace_cached_credentials(
    identity_client: FakeCognitoIdentityClient,
) -> None:
    identity_client.get_credentials_error = ClientError(
        {"Error": {"Code": "NotAuthorizedException", "Message": "nope"}},
        "GetCredentialsForIdentity",
    )
    manager = make_manager(
        auth_tokens=make_tokens(exp=NOW + timedelta(hours=1)),
        authenticator=FakeAuthenticator(responses=[]),
    )
    cached_credentials: cognito_mod.AWSCredentials = {
        "access_key_id": "old-access",
        "secret_access_key": "old-secret",
        "session_token": "old-session",
        "expiration": (NOW + timedelta(minutes=1)).isoformat(),
    }
    cached_response = make_aws_response(
        generation=99,
        exp=NOW + timedelta(minutes=1),
    )
    manager.credentials = cached_credentials
    manager.creds_response = cached_response

    with pytest.raises(ConnectionError, match="Failed to get AWS credentials"):
        manager.ensure_credentials(role_suffix="UploadRole")

    assert manager.credentials is cached_credentials
    assert manager.creds_response is cached_response


def test_refresh_token_request_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posted: dict[str, Any] = {}

    class FakeResponse:
        status_code = 200
        text = "ok"

        @staticmethod
        def json() -> dict[str, str]:
            return {
                "id_token": "id-2",
                "access_token": "access-2",
            }

    def fake_post(
        url: str,
        *,
        data: dict[str, str],
        headers: dict[str, str],
        auth: None,
        timeout: int,
    ) -> FakeResponse:
        posted.update(
            {
                "url": url,
                "data": data,
                "headers": headers,
                "auth": auth,
                "timeout": timeout,
            }
        )
        return FakeResponse()

    monkeypatch.setattr(cognito_mod.requests, "post", fake_post)
    authenticator = CognitoOAuthAuthenticator(
        cognito_domain="example.auth.us-east-1.amazoncognito.com",
        client_id="client-1",
    )

    tokens = authenticator.refresh_tokens("refresh-1")

    assert posted["url"] == authenticator.token_endpoint
    assert posted["data"] == {
        "client_id": "client-1",
        "grant_type": "refresh_token",
        "refresh_token": "refresh-1",
    }
    assert posted["headers"] == {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    assert posted["auth"] is None
    assert posted["timeout"] == 15
    assert tokens["refresh_token"] == "refresh-1"


def test_refresh_token_request_non_200_response_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        status_code = 400
        text = "invalid_grant"

        @staticmethod
        def json() -> dict[str, str]:
            raise AssertionError("error response should not be decoded")

    monkeypatch.setattr(
        cognito_mod.requests,
        "post",
        lambda *args, **kwargs: FakeResponse(),
    )
    authenticator = CognitoOAuthAuthenticator(
        cognito_domain="example.auth.us-east-1.amazoncognito.com",
        client_id="client-1",
    )

    with pytest.raises(PermissionError, match="Token refresh failed"):
        authenticator.refresh_tokens("refresh-1")
