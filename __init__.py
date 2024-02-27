"""A Synapse Admin API client library."""

# SPDX-FileCopyrightText: 2024 Joe Pitt
#
# SPDX-License-Identifier: GPL-3.0-only

# pylint: disable=too-many-lines
# Will consider how to sensibly split into multiple module files later.

from datetime import datetime, timedelta
from hmac import new as hmac
from hashlib import sha1
from time import sleep
from typing import Any, Dict, Final, List, Literal, Optional, Union
from validators import url  # type: ignore

from requests import (
    delete as http_delete,
    get as http_get,
    post as http_post,
    put as http_put,
    Response,
)
from requests.exceptions import JSONDecodeError

from . import __version__, endpoints
from .exceptions import (
    APIError,
    BadAccessTokenError,
    BadRequestError,
    EndpointNotFoundError,
    NonJSONResponseError,
    PurgeJobFailedError,
    RoomDeletionError,
)


class BackgroundUpdateStatus:
    """The status of a background update on the homeserver"""

    def __init__(self, db_name: str, json: Dict[str, Union[str, int, float]]) -> None:
        self._db_name: str = db_name
        self._name: str = str(json["name"])
        self._total_item_count: int = int(json["total_item_count"])
        self._total_duration_ms: float = float(json["total_duration_ms"])
        self._average_items_per_ms: float = float(json["average_items_per_ms"])

    def __str__(self) -> str:
        return self._name

    @property
    def db_name(self) -> str:
        """The database name.

        Usually Synapse is configured with a single database named 'master'"""
        return self.db_name

    @property
    def duration(self) -> float:
        """How long the background process has been running in milliseconds, excl. sleeping."""
        return self._total_duration_ms

    @property
    def name(self) -> str:
        """The name of the update."""
        return self._name

    @property
    def items(self) -> int:
        """The number of "items" processed (the meaning of 'items' depends on the operation)."""
        return self._total_item_count

    @property
    def items_per_ms(self) -> float:
        """How many items are processed per millisecond based on an exponential average."""
        return self._average_items_per_ms


class Event:
    """Details of changes to a room's state."""

    # All arguments required to create an Event
    # pylint: disable-next=too-many-arguments
    def __init__(
        self,
        homeserver: "Homeserver",
        room_id: str,
        event_id: str,
        origin_server_ts: int,
        event_type: str,
        user_id: str,
        content: Dict[str, Any],
    ) -> None:
        self._homeserver: Final[Homeserver] = homeserver
        self._room_id: Final[str] = room_id
        self._event_id: Final[str] = event_id
        self._origin_server_ts: Final[int] = origin_server_ts
        self._type: Final[str] = event_type
        self._user_id: Final[str] = user_id
        self._content: Dict[str, Any] = content

    @classmethod
    def from_dict(
        cls, homeserver: "Homeserver", source_object: Dict[str, Any]
    ) -> "Event":
        """Create an Event from a dictionary returned by the API.

        Args:
            homeserver (Homeserver): The Homeserver the Event is from.
            source_object (Dict[str, Any]): The dictionary returned by the API.

        Returns:
            Event: The generated Event.
        """

        return cls(
            homeserver,
            source_object["room_id"],
            source_object["event_id"],
            source_object["origin_server_ts"],
            source_object["type"],
            source_object["user_id"],
            source_object["content"],
        )

    @classmethod
    def from_event_report(
        cls, homeserver: "Homeserver", event_report: Dict[str, Any]
    ) -> "Event":
        """Create an Event from an event report returned by the API.

        Args:
            homeserver (Homeserver): The Homeserver the event report is from.
            source_object (Dict[str, Any]): The event report returned by the API.

        Returns:
            Event: The generated Event.
        """

        return Event(
            homeserver,
            event_report["room_id"],
            event_report["event_id"],
            event_report["event_json"].pop("origin_server_ts"),
            event_report["event_json"].pop("type"),
            event_report["sender"],
            event_report["event_json"],
        )

    def __str__(self) -> str:
        if isinstance(self.body, str):
            return self.body
        if "content" in self._content:
            return f"{self.event_type}: {self.content['content']}"
        return f"{self.event_type}: {self.content}"

    @property
    def body(self) -> Optional[str]:
        """The body of the message where it has one."""
        if self.encrypted:
            return "<Encrypted>"
        try:
            if self._content["msgtype"] == "m.text":
                return self._content["body"]
            return None
        except KeyError:
            pass
        try:
            if self._content["content"]["msgtype"] == "m.text":
                return self._content["content"]["body"]
            return None
        except KeyError:
            return None

    @property
    def content(self) -> Dict[str, Any]:
        """Details of the state change."""
        return self._content

    @property
    def encrypted(self) -> bool:
        """If the event is encrypted."""
        return self.event_type == "m.room.encrypted"

    @property
    def event_id(self) -> str:
        """The ID of the state event."""
        return self._event_id

    @property
    def room(self) -> "Room":
        """The ID of the room the state change occurred in"""
        return Room(
            self._homeserver, self._room_id, self._homeserver.server_notices_user
        )

    @property
    def timestamp(self) -> datetime:
        """When the state change occurred."""
        return timestamp_ms_to_datetime(self._origin_server_ts)

    @property
    def event_type(self) -> str:
        """The type of state change that occurred."""
        return self._type

    @property
    def user(self) -> "User":
        """The user that triggered the state change."""
        return User(self._homeserver, self._user_id)


class EventReport:
    """An Event (Abuse) Report."""

    # pylint: disable=too-many-instance-attributes
    # All attributes are required for an Event Report.

    def __init__(self, homeserver: "Homeserver", report_id: int) -> None:
        self._homeserver = homeserver
        report: Dict[str, Any] = homeserver.api_get(
            endpoints.EVENT_REPORT_DETAILS.format(report_id=report_id)
        )
        self._id: Final[int] = report["id"]
        self._received_ts: Final[int] = report["received_ts"]
        self._room: Final[Room] = Room(homeserver, report["room_id"])
        self._event: Final[Event] = Event.from_event_report(homeserver, report)
        self._user: Final[User] = User(homeserver, report["user_id"])
        self._reason: Final[str] = report["reason"]
        self._score: Final[int] = report["score"]
        self._sender: Final[Union[User, str]]
        try:
            self._sender = User(homeserver, report["sender"])
        except ValueError:
            self._sender = report["sender"]
        context: Final[Dict[str, Any]] = self._homeserver.api_get(
            endpoints.EVENT_CONTEXT.format(
                room_id=self._room.id, event_id=self.event.event_id
            )
        )
        self._events_before: Final[List[Event]] = []
        for event in reversed(context["events_before"]):
            self._events_before.append(Event.from_dict(self._homeserver, event))
        self._events_after: Final[List[Event]] = []
        for event in context["events_after"]:
            self._events_after.append(Event.from_dict(self._homeserver, event))
        self._state: Final[List[Event]] = []
        for event in context["state"]:
            self._state.append(Event.from_dict(self._homeserver, event))

    def __str__(self) -> str:
        return f"Event Report: {self.id}"

    @property
    def event(self) -> Event:
        """The reported event."""
        return self._event

    @property
    def events_after(self) -> List[Event]:
        """The events that occurred immediately after the reported event"""
        return self._events_after

    @property
    def events_before(self) -> List[Event]:
        """The events that occurred immediately before the reported event"""
        return self._events_before

    @property
    def id(self) -> int:
        """ID of event report."""
        return self._id

    @property
    def reason(self) -> Optional[str]:
        """Comment made by the user in this report. May be blank."""
        if len(self._reason) == 0:
            return None
        return self._reason

    @property
    def received(self) -> datetime:
        """The timestamp when this report was sent."""
        return timestamp_ms_to_datetime(self._received_ts)

    @property
    def room(self) -> "Room":
        """The room in which the event being reported is located."""
        return self._room

    @property
    def score(self) -> int:
        """Content is reported based upon a negative score,
        where -100 is "most offensive" and 0 is "inoffensive"."""
        return self._score

    @property
    def score_string(self) -> str:
        """Human readable offensiveness score."""
        if self._score > -10:
            # 0 to -9
            return f"Inoffensive {self._score}"
        if self._score > -25:
            # -10 to -24
            return f"Questionable {self._score}"
        if self._score > -75:
            # -25 to -74
            return f"Offensive {self._score}"
        if self._score > -90:
            # -75 to -89
            return f"Highly Offensive {self._score}"
        # -90 to -100
        return f"Extremely Offensive {self._score}"

    @property
    def sender(self) -> "User":
        """This is the user who sent the original message/event that was reported."""
        if isinstance(self._sender, User):
            return self._sender
        if isinstance(self._sender, str):
            return User(self._homeserver, self._sender)
        raise TypeError("sender must be User or str")

    @property
    def state(self) -> List[Event]:
        """The state of the room at the latest event of event or events_after."""
        return self._state

    @property
    def user(self) -> "User":
        """This is the user who reported the event and wrote the reason."""
        return self._user

    def delete(self) -> bool:
        """Delete the event report from the homeserver.

        Returns:
            bool: If the event report was deleted successfully.
        """
        try:
            self._homeserver.api_delete(
                endpoints.EVENT_REPORT_DELETE.format(report_id=self.id)
            )
            return True
        except (NonJSONResponseError, EndpointNotFoundError, APIError):
            return False

    def server_notice_to_reporter(self, message: str) -> None:
        """Send a server notice to the user who reported the message.

        Args:
            message (str): The body of the server notice.
        """

        self._homeserver.api_post(
            endpoints.SERVER_NOTICE,
            json={
                "user_id": self.user.name,
                "content": {"msgtype": "m.text", "body": message},
            },
        )

    def server_notice_to_sender(self, message: str) -> None:
        """Send a server notice to the user who sent the reported message.

        Args:
            message (str): The body of the server notice.
        """

        self._homeserver.api_post(
            endpoints.SERVER_NOTICE,
            json={
                "user_id": self.sender.name,
                "content": {"msgtype": "m.text", "body": message},
            },
        )


class ExternalID:
    """An external identity associated with a Matrix user."""

    def __init__(self, auth_provider: str, external_id: str) -> None:
        self._auth_provider = auth_provider
        self._external_id = external_id

    def __str__(self) -> str:
        return f"{self._auth_provider}: {self._external_id}"

    @property
    def provider(self) -> str:
        """The external provider of the identity"""
        return self._auth_provider

    @property
    def provider_id(self) -> str:
        """The external provider issued identifier"""
        return self._external_id


# Homeserver is the root class with many possible actions provided by the upstream API
# pylint: disable-next=too-many-public-methods
class Homeserver:
    """A synapse homeserver"""

    # All arguments required to create a Homeserver
    # pylint: disable-next=too-many-arguments
    def __init__(
        self,
        access_token: str,
        host: str = "localhost",
        port: int = 8008,
        secure: bool = False,
        verify: Optional[bool] = None,
        notices_user: Optional[str] = None,
    ) -> None:
        """A synapse homeserver

        Args:
            access_token (str): An admin access token for the server
            host (str, optional): The hostname / FQDN of the homeserver. Defaults to localhost.
            port (int, optional): The port the homeserver is running on. Defaults to 8008.
            secure (bool, optional): If the server is using HTTPS. Defaults to False.
            verify (bool, optional): Whether to validate the HTTPS certificate of the homeserver.
                Defaults to False.
            notices_user (bool, optional): The user_id which sends server notices on the homeserver.

        Raises:
            ValueError: If the homeserver cannot be used.
        """

        self._base_url: str
        if secure:
            self._base_url = f"https://{host}:{port}"
        else:
            self._base_url = f"http://{host}:{port}"
        if not url(self._base_url):
            raise ValueError(f"{self._base_url} is not a valid homeserver URL")

        self._access_token: Final[str] = access_token
        self._verify = verify
        self._server_name: Final[str] = self.api_get(endpoints.SERVER_KEYS)[
            "server_name"
        ]
        self._server_version: Final[str] = self.api_get(endpoints.SERVER_VERSION)[
            "server_version"
        ]
        self._notices_user = notices_user

    @property
    def background_updates(self) -> bool:
        """The status of background updates on the homeserver.

        Returns:
            bool: Whether background updates are enabled.
        """

        response = self.api_get(endpoints.BACKGROUND_UPDATES_ENABLED)
        return response["enabled"]

    @property
    def base_url(self) -> str:
        """The base URL of the homeserver"""
        return self._base_url

    @property
    def current_background_updates(self) -> List[BackgroundUpdateStatus]:
        """Details of currently running background updates on the homeserver.

        Returns:
            List[BackgroundUpdateStatus]: The currently running background updates.
        """

        updates: List[BackgroundUpdateStatus] = []
        response = self.api_get(endpoints.BACKGROUND_UPDATES_STATUS)
        for name in response["current_updates"]:
            updates.append(
                BackgroundUpdateStatus(name, response["current_updates"][name])
            )
        return updates

    @property
    def event_reports(self) -> List[EventReport]:
        """Event reports on the Homeserver."""
        event_reports: List[EventReport] = []
        response: Dict[str, Any] = {}
        first = True
        while first or "next_token" in response:
            if first:
                response = self.api_get(
                    endpoints.EVENT_REPORTS,
                    {"dir": "f"},
                )
                first = False
            else:
                response = self.api_get(
                    endpoints.EVENT_REPORTS,
                    {"dir": "f", "from": response["next_token"]},
                )

            for report in response["event_reports"]:
                event_reports.append(EventReport(self, report["id"]))

        return event_reports

    @property
    def registration_tokens(self) -> List["RegistrationToken"]:
        """Registration tokens on the Homeserver."""
        registration_tokens: List[RegistrationToken] = []
        response = self.api_get(endpoints.REGISTRATION_TOKENS)
        for registration_token in response["registration_tokens"]:
            registration_tokens.append(
                RegistrationToken(
                    self,
                    registration_token["token"],
                    registration_token["uses_allowed"],
                    registration_token["pending"],
                    registration_token["completed"],
                    registration_token["expiry_time"],
                )
            )
        return registration_tokens

    @property
    def rooms(self) -> List["Room"]:
        """Local and remote rooms on the Homeserver."""
        rooms: List[Room] = []
        response: Dict[str, Any] = {}
        first = True
        while first or "next_batch" in response:
            if first:
                response = self.api_get(endpoints.ROOMS)
                first = False
            else:
                response = self.api_get(
                    endpoints.ROOMS, {"from": response["next_batch"]}
                )
            for room in response["rooms"]:
                rooms.append(Room(self, room["room_id"], self._notices_user))
        return rooms

    @property
    def server_name(self) -> str:
        """The server's name e.g. matrix.org"""
        return self._server_name

    @property
    def server_notices_user(self) -> Optional[str]:
        """The user used to send Server Notices on the Homeserver."""
        return self._notices_user

    @property
    def server_version(self) -> str:
        """The version of synapse running on the server"""
        return self._server_version

    @staticmethod
    def _generate_registration_mac(
        shared_secret: str,
        nonce: str,
        username: str,
        password: str,
        admin: bool = False,
    ) -> str:
        """Generate a HMAC_SHA1 digest for account registration.

        Args:
            shared_secret (str): The homeserver's registration shared secret.
            nonce (str): A nonce from the homeserver.
            username (str): The new username.
            password (str): The new user's password.
            admin (bool, optional): If the new user will be an admin. Defaults to False.

        Returns:
            str: the digest as hexadecimal digits
        """
        mac = hmac(
            key=shared_secret.encode("utf8"),
            digestmod=sha1,
        )

        mac.update(nonce.encode("utf8"))
        mac.update(b"\x00")
        mac.update(username.encode("utf8"))
        mac.update(b"\x00")
        mac.update(password.encode("utf8"))
        mac.update(b"\x00")
        mac.update(b"admin" if admin else b"notadmin")

        return mac.hexdigest()

    @staticmethod
    def _handle_response(
        response: Response,
    ) -> Dict[str, Any]:
        if response.status_code == 200:
            try:
                return response.json()
            except JSONDecodeError as e:
                raise NonJSONResponseError() from e
        if response.status_code == 400:
            raise BadRequestError(response.json())
        if response.status_code == 404:
            raise EndpointNotFoundError()
        if response.status_code == 408:
            raise BadAccessTokenError()
        raise APIError(response.status_code, response.content)

    def api_delete(
        self,
        uri: str,
        parameters: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Performs an authenticated DELETE request against the homeserver.

        Args:
            uri (str): The URI to DELETE
            parameters (dict, optional): Any URI query string parameters to include.
                Defaults to None.
            json (dict, optional): The body to POST to the API. Defaults to None.

        Raises:
            NonJSONResponseError: If the response from the API is not well-formed JSON.
            EndpointNotFoundError: If the API responds with a 404 status code.
            BadAccessTokenError: If the API rejects the access token provided.
            APIError: If the API responds in an unexpected way.

        Returns:
            Dict[str, Any]: The body of the API's response, converted to a dict or list
        """

        request_url = f"{self._base_url}/{uri}"

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "User-Agent": f"PySynapse/{__version__.__version__}",
        }
        if json is not None:
            headers["Content-Type"] = "application/json"

        if self._verify is None:
            response = http_delete(
                request_url, params=parameters, headers=headers, timeout=5, json=json
            )
        else:
            response = http_delete(
                request_url,
                params=parameters,
                headers=headers,
                timeout=5,
                verify=self._verify,
                json=json,
            )

        return self._handle_response(response)

    def api_get(
        self,
        uri: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Performs an authenticated GET request against the homeserver.

        Args:
            uri (str): The URI to GET
            parameters (dict, optional): Any URI query string parameters to include.
                Defaults to None.

        Raises:
            NonJSONResponseError: If the response from the API is not well-formed JSON.
            EndpointNotFoundError: If the API responds with a 404 status code.
            BadAccessTokenError: If the API rejects the access token provided.
            APIError: If the API responds in an unexpected way.

        Returns:
            Dict[str, Any]: The body of the API's response, converted to a dict or list
        """

        request_url = f"{self._base_url}/{uri}"

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "User-Agent": f"PySynapse/{__version__.__version__}",
        }

        if self._verify is None:
            response = http_get(
                request_url, params=parameters, headers=headers, timeout=5
            )
        else:
            response = http_get(
                request_url,
                params=parameters,
                headers=headers,
                timeout=5,
                verify=self._verify,
            )

        return self._handle_response(response)

    def api_post(
        self,
        uri: str,
        parameters: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Performs an authenticated POST request against the homeserver.

        Args:
            uri (str): The URI to POST to.
            parameters (dict, optional): Any URI query string parameters to include.
                Defaults to None.
            json (dict, optional): The body to POST to the API. Defaults to None.

        Raises:
            NonJSONResponseError: If the response from the API is not well-formed JSON.
            EndpointNotFoundError: If the API responds with a 404 status code.
            BadAccessTokenError: If the API rejects the access token provided.
            APIError: If the API responds in an unexpected way.

        Returns:
            Dict[str, Any]: The body of the API's response, converted to a dict or list
        """

        request_url = f"{self._base_url}/{uri}"

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "User-Agent": f"PySynapse/{__version__.__version__}",
        }
        if json is not None:
            headers["Content-Type"] = "application/json"

        if self._verify is None:
            response = http_post(
                request_url, params=parameters, headers=headers, timeout=5, json=json
            )
        else:
            response = http_post(
                request_url,
                params=parameters,
                headers=headers,
                timeout=5,
                json=json,
                verify=self._verify,
            )

        return self._handle_response(response)

    def api_put(
        self,
        uri: str,
        parameters: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Performs an authenticated PUT request against the homeserver.

        Args:
            uri (str): The URI to PUT to.
            parameters (dict, optional): Any URI query string parameters to include.
                Defaults to None.
            json (dict, optional): The body to PUT to the API. Defaults to None.

        Raises:
            NonJSONResponseError: If the response from the API is not well-formed JSON.
            EndpointNotFoundError: If the API responds with a 404 status code.
            BadAccessTokenError: If the API rejects the access token provided.
            APIError: If the API responds in an unexpected way.

        Returns:
            Dict[str, Any]: The body of the API's response, converted to a dict or list
        """

        request_url = f"{self._base_url}/{uri}"

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "User-Agent": f"PySynapse/{__version__.__version__}",
        }
        if json is not None:
            headers["Content-Type"] = "application/json"

        if self._verify is None:
            response = http_put(
                request_url, params=parameters, headers=headers, timeout=5, json=json
            )
        else:
            response = http_put(
                request_url,
                params=parameters,
                headers=headers,
                timeout=5,
                json=json,
                verify=self._verify,
            )

        return self._handle_response(response)

    # Time arguments split for ease of use
    # pylint: disable-next=too-many-arguments
    def delete_media_by_age(
        self,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        larger_than: int = 0,
        keep_profiles: bool = True,
    ) -> int:
        """Delete media that hasn't been used for more than the specified time.

        Args:
            self (self): The self to delete from
            days (int, optional): The number of days since last use before deletion.
            hours (int, optional): The number of hours since last use before deletion.
            minutes (int, optional): The number of minutes since last use before deletion.
            seconds (int, optional): The number of seconds since last use before deletion.
            larger_than (int, optional): The minimum file size to delete. Defaults to 0.
            keep_profiles (bool, optional): Whether to keep files that are still used in image data
                (e.g user profile, room avatar). Defaults to True.

        Raises:
            ValueError: If no retention time is given.

        Returns:
            int: The number of items deleted.
        """

        delta = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        if delta.total_seconds() == 0:
            raise ValueError(
                "At least one of days, hours, minutes, or seconds must be specified"
            )

        before = datetime.now() - delta
        before_ms = datetime_to_timestamp_ms(before)
        filters = {
            "before_ts": before_ms,
            "size_gt": larger_than,
            "keep_profiles": keep_profiles,
        }
        return self.api_delete(endpoints.MEDIA_DELETE, filters)["total"]

    def delete_media_by_id(self, media_id: str) -> bool:
        """Delete a media item by its ID.

        Args:
            self (self): The self to delete from.
            media_id (str): The ID of the item to delete.

        Returns:
            bool: If the item was deleted successfully.
        """

        if (
            self.api_delete(
                endpoints.MEDIA_ITEM.format(
                    server_id=self.server_name, media_id=media_id
                )
            )["total"]
            > 0
        ):
            return True
        return False

    def delete_media_by_user(self, user: Union["User", str], limit: int = 100) -> int:
        """Delete all media created by a user.

        Args:
            self (self): The home server to delete from.
            user (User | str): The user who's media should be deleted.
            limit (int, optional): The maximum number of items to delete. Defaults to 100.

        Returns:
            int: How many items were deleted
        """

        if isinstance(user, User):
            return self.api_delete(
                endpoints.USER_MEDIA.format(user_id=user.name), {"limit": limit}
            )["total"]
        if isinstance(user, str):
            return self.api_delete(
                endpoints.USER_MEDIA.format(user_id=user), {"limit": limit}
            )["total"]
        raise TypeError("user must be a User or a str")

    def disable_background_updates(self) -> bool:
        """Disables background updates on the homeserver

        Returns:
            bool: If background updates were disabled successfully
        """

        response = self.api_post(
            endpoints.BACKGROUND_UPDATES_ENABLED, json={"enabled": False}
        )
        return not response["enabled"]

    def download_media(self, media_id: str, save_to: str) -> bool:
        """Download a media item to a file.

        Args:
            media_id (str): The ID of the media item.
            save_to (str): The path to save the media item to.

        Returns:
            bool: Whether the file was downloaded successfully.
        """

        try:
            with open(save_to, "wb") as f:
                uri = endpoints.MEDIA_DOWNLOAD.format(
                    server_name=self.server_name, media_id=media_id
                )
                request_url = f"{self._base_url}/{uri}"
                response = http_get(request_url, timeout=5)
                if response.status_code == 200:
                    f.write(response.content)
                else:
                    return False
            return True
        except (PermissionError, OSError):
            return False

    def enable_background_updates(self) -> bool:
        """Enables background updates on the homeserver

        Returns:
            bool: If background updates were enabled successfully
        """

        response = self.api_post(
            endpoints.BACKGROUND_UPDATES_ENABLED, json={"enabled": True}
        )
        return response["enabled"]

    def populate_stats_process_rooms(self) -> None:
        """Recalculate the stats for all rooms."""
        self.api_post(
            endpoints.BACKGROUND_UPDATES_RUN,
            json={"job_name": "populate_stats_process_rooms"},
        )

    def protect_media_from_quarantine(self, media_id: str) -> bool:
        """Protects a piece of local media from being quarantined.

        Args:
            self (self): The self to perform the action on.
            media_id (str): The ID of the media item to protect.

        Returns:
            bool: If protection was enabled successfully.
        """

        try:
            self.api_post(endpoints.MEDIA_PROTECT.format(media_id=media_id))
            return True
        except BadRequestError:
            return False

    def purge_media_cache(
        self,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
    ) -> int:
        """Purge old cached remote media.

        Args:
            self (self): The self to clear the cache on.
            days (int, optional): The number of days since last access to keep cached.
                Defaults to 0.
            hours (int, optional): The number of hours since last access to keep cached.
                Defaults to 0.
            minutes (int, optional): The number of minutes since last access to keep cached.
                Defaults to 0.
            seconds (int, optional): The number of seconds since last access to keep cached.
                Defaults to 0.

        Raises:
            ValueError: If no retention time is given.

        Returns:
            int: The number of items purged from the cache.
        """

        delta = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        if delta.total_seconds() == 0:
            raise ValueError(
                "At least one of days, hours, minutes, or seconds must be specified"
            )

        before = datetime.now() - delta
        before_ms = datetime_to_timestamp_ms(before)
        filters = {"before_ts": before_ms}
        return self.api_post(endpoints.MEDIA_PURGE_CACHE, filters)["deleted"]

    def regenerate_directory(self) -> None:
        """Recalculate the user directory if it is stale or out of sync."""
        self.api_post(
            endpoints.BACKGROUND_UPDATES_RUN,
            json={"job_name": "regenerate_directory"},
        )

    # All arguments required to register a User
    # pylint: disable-next=too-many-arguments
    def register_user(
        self,
        registration_secret: str,
        username: str,
        password: str,
        display_name: Optional[str] = None,
        admin: bool = False,
    ) -> str:
        """Register a new user on the homeserver.

        Args:
            registration_secret (str): The homeserver's registration secret.
            username (str): The new user's username.
            password (str): The new user's password.
            display_name (str, optional): The new user's display name. Defaults to None.
            admin (bool, optional): If the new user will be an admin. Defaults to False.

        Returns:
            str: The new user's access token.
        """

        nonce = self.api_get(endpoints.REGISTER_USER)["nonce"]
        mac = self._generate_registration_mac(
            registration_secret, nonce, username, password, admin
        )
        registration_data = {
            "nonce": nonce,
            "username": username,
            "password": password,
            "admin": admin,
            "mac": mac,
        }
        if display_name is not None:
            registration_data["displayname"] = display_name

        return self.api_post(endpoints.REGISTER_USER, json=registration_data)[
            "access_token"
        ]

    def renew_account(
        self,
        user: Union["User", str],
        expiration: Union[datetime, int, None],
        enable_renewal_emails: bool = True,
    ) -> datetime:
        """Extend the validity of an account.

        Args:
            access_token (str): The access token to authenticate to the homeserver with
            user (Union[User, str]): _description_
            expiration (Union[datetime, int, None]): _description_
            enable_renewal_emails (bool, optional): _description_. Defaults to True.

        Raises:
            TypeError: _description_
            TypeError: _description_
            TypeError: _description_
            APIError: _description_

        Returns:
            datetime: _description_
        """
        data: Dict[str, Any] = {}

        if isinstance(user, User):
            data["user_id"] = user.name
        elif isinstance(user, str):
            data["user_id"] = user
        else:
            raise TypeError("user_id must be User or str")

        if isinstance(expiration, datetime):
            data["expiration_ts"] = datetime_to_timestamp_ms(expiration)
        elif isinstance(expiration, int):
            data["expiration_ts"] = expiration
        elif expiration is None:
            pass
        else:
            raise TypeError("expiration must be datetime, int, or None")

        if isinstance(enable_renewal_emails, bool):
            data["enable_renewal_emails"] = enable_renewal_emails
        else:
            raise TypeError("enable_renewal_emails must be bool")

        response = self.api_post(endpoints.RENEW_ACCOUNT, json=data)
        if "expiration_ts" in response:
            return timestamp_ms_to_datetime(response["expiration_ts"])
        raise APIError()

    def quarantine_media_by_id(
        self, media_id: str, server_name: Optional[str] = None
    ) -> bool:
        """Quarantines a piece of local or remote media.

        Args:
            self (self): The self to act on.
            media_id (str): The ID of the media to quarantine.
            server_name (str, optional): The server name the media originated from.
                Defaults to `self.server_name`.

        Returns:
            bool: If the media was successfully quarantined.
        """

        if server_name is None:
            server_name = self.server_name

        try:
            self.api_post(
                endpoints.MEDIA_QUARANTINE.format(
                    server_name=server_name, media_id=media_id
                )
            )
            return True
        except BadRequestError:
            return False

    def quarantine_media_by_room(
        self, room: Union["Room", str]
    ) -> Union[int, Literal[False]]:
        """Quarantine all local and remote media in a room.

        Args:
            self (self): The self to act on.
            room (Room | str): The target room.

        Raises:
            TypeError: If room is an invalid type.

        Returns:
            int: The number of items quarantined.
            Literal[False]: If the quarantining failed.
        """
        if isinstance(room, Room):
            room_id = room.id
        elif isinstance(room, str):
            room_id = room
        else:
            raise TypeError("room must be a Room or a str")

        try:
            return self.api_post(
                endpoints.MEDIA_QUARANTINE_ROOM.format(room_id=room_id)
            )["num_quarantined"]
        except BadRequestError:
            return False

    def quarantine_media_by_user(
        self, user: Union["User", str]
    ) -> Union[int, Literal[False]]:
        """Quarantine all local and remote media from a user.

        Args:
            self (self): The self to act on.
            user (User | str): The target user.

        Raises:
            TypeError: If user is an invalid type.

        Returns:
            int: The number of items quarantined.
            Literal[False]: If the quarantining failed.
        """
        if isinstance(user, User):
            user_id = user.name
        elif isinstance(user, str):
            user_id = user
        else:
            raise TypeError("user must be a User or a str")

        try:
            return self.api_post(
                endpoints.MEDIA_QUARANTINE_USER.format(user_id=user_id)
            )["num_quarantined"]
        except BadRequestError:
            return False

    def unprotect_media_from_quarantine(self, media_id: str) -> bool:
        """Remove protection of a piece of local media from being quarantined.

        Args:
            self (self): The self to perform the action on.
            media_id (str): The ID of the media item to remove protection form.

        Returns:
            bool: If protection was removed successfully.
        """

        try:
            self.api_post(endpoints.MEDIA_UNPROTECT.format(media_id=media_id))
            return True
        except BadRequestError:
            return False

    def unquarantine_media_by_id(
        self, media_id: str, server_name: Optional[str] = None
    ) -> bool:
        """Releases a quarantined piece of local or remote media.

        Args:
            self (self): The self to act on.
            media_id (str): The ID of the media to release from quarantine.
            server_name (str, optional): The server name the media originated from.
                Defaults to `self.server_name`.

        Returns:
            bool: If the media was successfully released from quarantine.
        """

        if server_name is None:
            server_name = self.server_name

        try:
            self.api_post(
                endpoints.MEDIA_UNQUARANTINE.format(
                    server_name=server_name, media_id=media_id
                )
            )
            return True
        except BadRequestError:
            return False


class RegistrationToken:
    """A token granting access to register a user account"""

    # All arguments required to create a Registration Token
    # pylint: disable-next=too-many-arguments
    def __init__(
        self,
        homeserver: Homeserver,
        token: str,
        uses_allowed: int,
        pending: int,
        completed: int,
        expiry_time: int,
    ) -> None:
        self._homeserver: Final[Homeserver] = homeserver
        self._token: str = token
        self._uses_allowed: Optional[int] = uses_allowed
        self._pending: Final[int] = pending
        self._completed: Final[int] = completed
        self._expiry_time: Optional[int] = expiry_time

    # All arguments required to create a Registration Token
    @classmethod
    # pylint: disable-next=too-many-arguments
    def create(
        cls,
        homeserver: Homeserver,
        token: Optional[str] = None,
        length: Optional[int] = None,
        uses_allowed: Optional[int] = None,
        expiry_time: Optional[datetime] = None,
    ) -> "RegistrationToken":
        """Create a new registration token on the homeserver.

        Args:
            homeserver (Homeserver): The homeserver to create the token on.
            token (str, optional): The token value to use. Defaults to randomly generated.
            length (int, optional): The length of the generated token. Defaults to 16.
            uses_allowed (int, optional): The number of uses allowed with the token.
                Defaults to unlimited.
            expiry_time (datetime, optional): When the token should expire. Defaults to never.

        Returns:
            RegistrationToken: The newly created token.
        """

        token_data: Dict[str, Any] = {}
        if token is not None:
            token_data["token"] = token
        if length is not None:
            token_data["length"] = length
        if uses_allowed is not None:
            token_data["uses_allowed"] = uses_allowed
        if expiry_time is not None:
            token_data["expiry_time"] = datetime_to_timestamp_ms(expiry_time)
        response = homeserver.api_post(
            endpoints.REGISTRATION_TOKEN_CREATE, json=token_data
        )
        return cls(
            homeserver=homeserver,
            token=response["token"],
            uses_allowed=response["uses_allowed"],
            pending=response["pending"],
            completed=response["completed"],
            expiry_time=response["expiry_time"],
        )

    @classmethod
    def load(cls, homeserver: Homeserver, token: str) -> "RegistrationToken":
        """Load a token from the homeserver.

        Args:
            homeserver (Homeserver): The homeserver to load the token from.
            token (str): The token to load.

        Returns:
            RegistrationToken: The loaded token
        """
        response = homeserver.api_get(endpoints.REGISTRATION_TOKEN.format(token=token))
        return cls(
            homeserver=homeserver,
            token=response["token"],
            uses_allowed=response["uses_allowed"],
            pending=response["pending"],
            completed=response["completed"],
            expiry_time=response["expiry_time"],
        )

    def __str__(self) -> str:
        if self.valid:
            return self._token
        return f"{self._token} (invalid)"

    @property
    def completed_registrations(self) -> int:
        """How many registrations have completed using this token."""
        return self._completed

    @property
    def expires(self) -> Optional[datetime]:
        """When the token expires. None for never."""
        if self._expiry_time is not None:
            return timestamp_ms_to_datetime(self._expiry_time)
        return None

    @property
    def pending_registrations(self) -> int:
        """How many partially complete registrations are using this token."""
        return self._pending

    @property
    def token(self) -> str:
        """The token value"""
        return self._token

    @property
    def uses_allowed(self) -> Optional[int]:
        """The total allowed registrations for this token. None for unlimited."""
        if self._uses_allowed is not None:
            return self._uses_allowed
        return None

    @property
    def uses_left(self) -> Optional[int]:
        """The number of registrations remaining. None for unlimited."""
        if self._uses_allowed is not None:
            return self._uses_allowed - self._pending - self._completed
        return None

    @property
    def valid(self) -> bool:
        """If the Registration Token is still valid."""
        return self.uses_left is not None and self.uses_left > 0

    def allow_unlimited_uses(self) -> None:
        """Allow unlimited uses of this token."""

        self._homeserver.api_put(
            endpoints.REGISTRATION_TOKEN.format(token=self.token),
            json={"uses_allowed": None},
        )
        self._uses_allowed = None

    def delete(self) -> None:
        """Delete this token"""
        self._homeserver.api_delete(
            endpoints.REGISTRATION_TOKEN.format(token=self._token)
        )
        self._token = "<deleteD>"
        self._uses_allowed = -1
        self._expiry_time = 0

    def invalidate(self) -> None:
        """Invalidate this token."""

        self._homeserver.api_put(
            endpoints.REGISTRATION_TOKEN.format(token=self.token),
            json={"uses_allowed": 0},
        )
        self._uses_allowed = 0

    def never_expire(self) -> None:
        """Make this token valid indefinitely"""

        self._homeserver.api_put(
            endpoints.REGISTRATION_TOKEN.format(token=self.token),
            json={"expiry_time": None},
        )
        self._expiry_time = None

    def set_expiry_time(self, expiry_time: datetime) -> None:
        """Set the expiry time for this token.

        Args:
            expiry_time (datetime): The new expiry time.
        """

        self._homeserver.api_put(
            endpoints.REGISTRATION_TOKEN.format(token=self.token),
            json={"expiry_time": int(datetime_to_timestamp_ms(expiry_time))},
        )
        self._expiry_time = int(datetime_to_timestamp_ms(expiry_time))

    def set_uses_allowed(self, uses_allowed: int) -> None:
        """Set the number of uses allowed for this token.

        Args:
            uses_allowed (int): The number of uses to allow.
        """

        self._homeserver.api_put(
            endpoints.REGISTRATION_TOKEN.format(token=self.token),
            json={"uses_allowed": uses_allowed},
        )
        self._uses_allowed = uses_allowed


# Rooms have many possible actions provided by the upstream API
# pylint: disable-next=too-many-public-methods
class Room:
    """A room on a synapse matrix server."""

    # pylint: disable=too-many-instance-attributes
    # All attributes are required for a Room.

    def __init__(
        self, homeserver: Homeserver, room_id: str, notices_user: Optional[str] = None
    ) -> None:
        response = homeserver.api_get(endpoints.ROOM_DETAILS.format(room_id=room_id))
        self._avatar: Final[Optional[str]] = response["avatar"]
        self._canonical_alias: Final[Optional[str]] = response["canonical_alias"]
        self._creator: Final[str] = response["creator"]
        self._encryption: Final[Optional[str]] = response["encryption"]
        self._federatable: Final[bool] = response["federatable"]
        self._forgotten: Final[bool] = response["forgotten"]
        self._guest_access: Final[str] = response["guest_access"]
        self._history_visibility: Final[str] = response["history_visibility"]
        self._homeserver: Final[Homeserver] = homeserver
        self._id: Final[str] = room_id
        self._join_rules: Final[str] = response["join_rules"]
        self._joined_local_devices: Final[int] = response["joined_local_devices"]
        self._joined_local_members: Final[int] = response["joined_local_members"]
        self._joined_members: Final[int] = response["joined_members"]
        self._name: Final[Optional[str]] = response["name"]
        self._public: Final[bool] = response["public"]
        self._room_type: Final[Optional[str]] = response["room_type"]
        self._state_events: Final[int] = response["state_events"]
        self._topic: Final[Optional[str]] = response["topic"]
        self._version: Final[int] = int(response["version"])

        members = homeserver.api_get(endpoints.ROOM_MEMBERS.format(room_id=room_id))[
            "members"
        ]
        self._members: Final[List[str]] = []
        for member in members:
            self._members.append(member)

        if (
            notices_user is not None
            and self._joined_members == 1
            and notices_user in self._members
        ) or self._joined_members == 0:
            self._forgotten = True

    def __str__(self) -> str:
        if self._name is not None and self._canonical_alias is not None:
            return f"{self._name} ({self._canonical_alias}) [{self._id}]"
        if self._name is not None and self._canonical_alias is None:
            return f"{self._name} [{self._id}]"
        if self._name is None and self._canonical_alias is not None:
            return f"{self._canonical_alias} [{self._id}]"
        return self._id

    @property
    def avatar_url(self) -> Optional[str]:
        """The `mxc` URI to the avatar of the room."""
        return self._avatar

    @property
    def blocked(self) -> bool:
        """If users are currently blocked from joining the room."""
        return self._homeserver.api_get(endpoints.ROOM_BLOCK.format(room_id=self.id))[
            "block"
        ]

    @property
    def blocked_by(self) -> Optional["User"]:
        """If users are blocked from joining the room, the user who blocked this."""
        try:
            return User(
                self._homeserver,
                self._homeserver.api_get(endpoints.ROOM_BLOCK.format(room_id=self.id))[
                    "user_id"
                ],
            )
        except KeyError:
            return None

    @property
    def canonical_alias(self) -> Optional[str]:
        """The canonical (main) alias address of the room."""
        return self._canonical_alias

    @property
    def creator(self) -> "User":
        """The room's creator."""
        return User(self._homeserver, self._creator)

    @property
    def encrypted(self) -> bool:
        """If the room has encryption enabled."""
        return self._encryption is not None

    @property
    def encryption_algorithm(self) -> Optional[str]:
        """Algorithm of end-to-end encryption of messages."""
        return self._encryption

    @property
    def federatable(self) -> bool:
        """Whether users on other servers can join this room."""
        return self._federatable

    @property
    def forgotten(self) -> bool:
        """Whether all local users have forgotten the room."""
        return self._forgotten

    @property
    def guest_access(self) -> bool:
        """Whether guests can join the room."""
        return self._guest_access == "can_join"

    @property
    def history_visibility(self) -> str:
        """Who can see the room history.

        Values:
           - invited
           - joined
           - shared
           - world_readable"""
        return self._history_visibility

    @property
    def id(self) -> str:
        """The ID of the room."""
        return self._id

    @property
    def is_space(self) -> bool:
        """If the room is a space."""
        return self._room_type == "m.space"

    @property
    def join_rules(self) -> str:
        """The type of rules used for users wishing to join this room.

        Values:
            - public
            - knock
            - invite
            - private
        """
        return self._join_rules

    @property
    def local_devices(self) -> int:
        """How many local devices are currently in the room."""
        return self._joined_local_devices

    @property
    def local_members(self) -> int:
        """How many local users are currently in the room."""
        return self._joined_local_members

    @property
    def member_count(self) -> int:
        """How many users are currently in the room."""
        return self._joined_members

    @property
    def members(self) -> List["User"]:
        """List of members currently in the room."""

        users: List[User] = []
        for user in self._members:
            users.append(User(self._homeserver, user))
        return users

    @property
    def messages(self) -> List[Event]:
        """Messages sent in the room."""
        messages: List[Event] = []
        response: Dict[str, Any] = {}
        first = True
        while first or "end" in response:
            if first:
                response = self._homeserver.api_get(
                    endpoints.ROOM_MESSAGES.format(room_id=self._id), {"limit": 100}
                )
                first = False
            else:
                response = self._homeserver.api_get(
                    endpoints.ROOM_MESSAGES.format(room_id=self._id),
                    {"limit": 100, "from": response["end"]},
                )
            for event in response["chunk"]:
                messages.append(Event.from_dict(self._homeserver, event))
        return messages

    @property
    def name(self) -> Optional[str]:
        """The name of the room."""
        return self._name

    @property
    def public(self) -> bool:
        """Whether the room is visible in room directory."""
        return self._public

    @property
    def state_event_count(self) -> int:
        """Total number of state_events of a room. Complexity of the room."""
        return self._state_events

    @property
    def state_events(self) -> List[Event]:
        """State change events in the Room."""
        response = self._homeserver.api_get(
            endpoints.ROOM_STATE.format(room_id=self.id)
        )["state"]
        events: List[Event] = []
        for event in response:
            events.append(Event.from_dict(self._homeserver, event))
        return events

    @property
    def topic(self) -> Optional[str]:
        """The topic of the room."""
        return self._topic

    @property
    def room_type(self) -> Optional[str]:
        """The type of the room taken from the room's creation event.

        For example "m.space" if the room is a space."""
        return self._room_type

    @property
    def version(self) -> int:
        "The version of the room."
        return self._version

    def block(self) -> None:
        """Block users from joining the room."""
        self._homeserver.api_put(
            endpoints.ROOM_BLOCK.format(room_id=self.id), json={"block": True}
        )

    # All arguments required to delete a room
    # pylint: disable-next=too-many-arguments
    def delete(
        self,
        block_rejoining: bool = True,
        purge: bool = True,
        force_purge: Optional[bool] = False,
        new_room: bool = False,
        new_room_owner: Optional[str] = None,
        new_room_name: Optional[str] = None,
        new_room_message: Optional[str] = None,
    ) -> None:
        """Delete the room.

        Args:
            block_rejoining (bool, optional): Prevent future attempts to join the room.
                Defaults to True.
            purge (bool, optional): Remove all traces of the room from the database.
                Defaults to True.
            force_purge (bool, optional): Force a purge even with local users still in the room.
                Defaults to False.
            new_room (bool, optional): Creates a new room with all current members in.
                Defaults to False.
            new_room_owner (str, optional): Owner and admin of the new room.
                The user ID must be on the local server, but does not necessarily have to belong to
                a registered user.
                Defaults to self._homeserver.server_notices_user.
            new_room_name (str, optional): The name of the new room.
                Defaults to "Content Violation Notification".
            new_room_message (str, optional): The message that will be sent in the new room.
                Defaults to "Sharing illegal content on this server is not permitted and rooms in
                violation will be blocked".

        Returns:
            bool: If the room was deleted successfully.
        """
        delete_id = self.delete_async(
            block_rejoining,
            purge,
            force_purge,
            new_room,
            new_room_owner,
            new_room_name,
            new_room_message,
        )
        while not self.delete_async_complete(delete_id):
            sleep(2)

    # All arguments required to delete a room
    # pylint: disable-next=too-many-arguments
    def delete_async(
        self,
        block_rejoining: bool = True,
        purge: bool = True,
        force_purge: Optional[bool] = False,
        new_room: bool = False,
        new_room_owner: Optional[str] = None,
        new_room_name: Optional[str] = None,
        new_room_message: Optional[str] = None,
    ) -> str:
        """Trigger the asynchronous deletion of the room.

        Args:
            block_rejoining (bool, optional): Prevent future attempts to join the room.
                Defaults to True.
            purge (bool, optional): Remove all traces of the room from the database.
                Defaults to True.
            force_purge (bool, optional): Force a purge even if there are local users in the room.
                Defaults to False.
            new_room (bool, optional): Creates a new room with all current members in.
                Defaults to False.
            new_room_owner (str, optional): Owner and admin of the new room.
                The user ID must be on the local server, but does not necessarily have to belong to
                a registered user.
                Defaults to self._homeserver.server_notices_user.
            new_room_name (str, optional): The name of the new room.
                Defaults to "Content Violation Notification".
            new_room_message (str, optional): The message that will be sent in the new room.
                Defaults to "Sharing illegal content on this server is not permitted and rooms in
                violation will be blocked".

        Returns:
            bool: If the room was deleted successfully.
        """

        data: Dict[str, Union[str, bool]] = {"block": block_rejoining, "purge": purge}

        if purge and force_purge:
            data["force_purge"] = True

        if new_room:
            if new_room_owner is None:
                if self._homeserver.server_notices_user is None:
                    raise ValueError(
                        "No new room owner given and homeserver has no server notices user set"
                    )
                data["new_room_user_id"] = self._homeserver.server_notices_user
            else:
                data["new_room_user_id"] = new_room_owner

            if new_room_name is None:
                data["room_name"] = "Content Violation Notification"
            else:
                data["room_name"] = new_room_name

            if new_room_message is None:
                data["message"] = (
                    "Sharing illegal content on this server is not permitted and rooms in violation"
                    "will be blocked."
                )
            else:
                data["message"] = new_room_message

        return self._homeserver.api_delete(
            endpoints.ROOM_DELETE.format(room_id=self.id), json=data
        )["delete_id"]

    def delete_async_complete(self, delete_id: str) -> bool:
        """Check the status of a room deletion request.

        Args:
            delete_id (str): The ID of the delete request

        Raises:
            RoomDeletionError: If the room could not be deleted.
            APIError: If the response is not understood.

        Returns:
            bool: Whether the room deletion has completed yet.
        """

        response = self._homeserver.api_get(
            endpoints.ROOM_DELETE_STATUS.format(delete_id=delete_id)
        )
        if response["status"] == "complete":
            return True
        if response["status"] in ["shutting_down", "purging", "active"]:
            # active is an undocumented state seen when creating a new room
            return False
        if response["status"] == "failed":
            raise RoomDeletionError(response["error"])
        raise APIError(f"Unknown status {response['status']}")

    def get_message_by_timestamp(
        self, timestamp: datetime, before: bool = False
    ) -> Event:
        """Gets the closest event before or after (default) to the given timestamp.

        Args:
            timestamp (datetime): The reference point in time.
            before (bool, optional): Reverses search to the closest event before the timestamp.
                Defaults to False.

        Raises:
            ValueError: if no message matching the search is found in the room.

        Returns:
            Event: The event closet to the timestamp
        """

        filters: Dict[str, Any] = {"ts": datetime_to_timestamp_ms(timestamp)}
        if before:
            filters["dir"] = "b"

        event_id = self._homeserver.api_get(
            endpoints.ROOM_MESSAGE_BY_TIMESTAMP.format(room_id=self._id), filters
        )["event_id"]

        for message in self.messages:
            if message.event_id == event_id:
                return message

        raise ValueError("No matching message found")

    def invite(self, user: Union["User", str]) -> None:
        """Invite a user to this room. The authenticated user must be in the room.

        Args:
            user (User | str): The user to invite.
        """

        if isinstance(user, User):
            user_id = user.name
        else:
            user_id = user

        self._homeserver.api_post(
            endpoints.ROOM_INVITE_USER.format(room_id=self._id),
            json={"user_id": user_id},
        )

    def make_admin(self, user: Union["User", str]) -> None:
        """Make a user an admin of the room.

        Args:
            user (User | str): The user to make an admin.

        Raises:
            TypeError: If user is not a User or a str object.
        """

        if isinstance(user, User):
            user_id = user.name
        elif isinstance(user, str):
            user_id = user
        else:
            raise TypeError("user must be a User or str object")
        self._homeserver.api_post(
            endpoints.ROOM_MAKE_ADMIN.format(room_id=self.id), json={"user_id": user_id}
        )

    # Time arguments split for ease of use
    # pylint: disable-next=too-many-arguments
    def purge_history_by_age(
        self,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        delete_local_events: bool = False,
    ) -> str:
        """Purge historic events from the database based on their age.

        Args:
            days (int, optional): The number of days of history to retain. Defaults to 0.
            hours (int, optional): The number of hours of history to retain. Defaults to 0.
            minutes (int, optional): The number of minutes of history to retain. Defaults to 0.
            seconds (int, optional): The number of seconds of history to retain. Defaults to 0.
            delete_local_events (bool, optional): Whether to delete local events.
                Potentially the only copy of them.
                Defaults to False.

        Raises:
            TypeError: If room is not a valid type.
            ValueError: If no age is provided.

        Returns:
            str: The ID of the purge job that was started.
        """

        delta = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
        if delta.total_seconds() == 0:
            raise ValueError(
                "At least one of days, hours, minutes, or seconds must be specified"
            )

        before = datetime.now() - delta
        before_ms = datetime_to_timestamp_ms(before)
        filters = {
            "delete_local_events": delete_local_events,
            "purge_up_to_ts": before_ms,
        }
        return self._homeserver.api_post(
            endpoints.ROOM_PURGE_HISTORY.format(room_id=self.id), json=filters
        )["purge_id"]

    def purge_history_by_event_id(
        self,
        event: Union[Event, str],
        delete_local_events: bool = False,
    ):
        """Purge historic events from the database up to, but excluding, the given event.

        Args:
            room (Room | str): The room to purge history from.
            event (Event | str): The earliest event to retain.
            delete_local_events (bool, optional): Whether to delete local events.
                Potentially the only copy of them.
                Defaults to False.

        Raises:
            TypeError: If room or event are not valid types.

        Returns:
            str: The ID of the purge job that was started.
        """

        if isinstance(event, Event):
            event_id = event.event_id
        elif isinstance(event, str):
            event_id = event
        else:
            raise TypeError("event must be a Event or a str")

        filters: Dict[str, Any] = {
            "delete_local_events": delete_local_events,
            "purge_up_to_event_id": event_id,
        }
        return self._homeserver.api_post(
            endpoints.ROOM_PURGE_HISTORY.format(room_id=self.id), json=filters
        )["purge_id"]

    def purge_history_finished(self, purge_id: str) -> bool:
        """Check if a history purge job has finished.

        Args:
            purge_id (str): The ID of the purge job.

        Raises:
            PurgeJobFailedError: If the job has failed.
            APIError: If the API responded in an unexpected way.

        Returns:
            bool: If the job has finished.
        """
        response = self._homeserver.api_get(
            endpoints.ROOM_PURGE_HISTORY_STATUS.format(purge_id=purge_id)
        )

        if response["status"] == "complete":
            return True
        if response["status"] == "active":
            return False
        if response["status"] == "failed":
            raise PurgeJobFailedError(response["error"])
        raise APIError(response)

    def unblock(self) -> None:
        """Unblock users from joining the room."""
        self._homeserver.api_put(
            endpoints.ROOM_BLOCK.format(room_id=self.id), json={"block": False}
        )


class ThreePID:
    """A third-party identity associated with a Matrix user."""

    def __init__(self, medium: str, address: str, added: int, validated: int) -> None:
        self._medium: Final[str] = medium
        self._address: Final[str] = address
        self._added: Final[int] = added
        self._validated: Final[Optional[int]] = validated

    def __str__(self) -> str:
        if self._validated is not None:
            return self._address
        return f"{self._address} (unverified)"

    @property
    def added(self) -> datetime:
        """When the third party ID was added"""
        return timestamp_ms_to_datetime(self._added)

    @property
    def address(self) -> str:
        """The third party ID"""
        return self._address

    @property
    def medium(self) -> str:
        """The third party ID type, like email"""
        return self._medium

    @property
    def validated(self) -> Optional[datetime]:
        """When the third party ID was validated"""
        if self._validated is not None:
            return timestamp_ms_to_datetime(self._validated)
        return None


class User:
    """A user on a Matrix server"""

    # All attributes are required for a User.
    # pylint: disable=too-many-instance-attributes

    # There are multiple ways that a user may need to be created depending if they still exist or
    # not and if they are local or remote if they do.
    # pylint: disable-next=too-many-statements
    def __init__(self, homeserver: Homeserver, user_id: str) -> None:
        self._homeserver: Final[Homeserver] = homeserver
        self._admin: Final[bool]
        self._appservice_id: Final[Optional[str]]
        self._avatar_url: Final[Optional[str]]
        self._consent_server_notice_sent: Final[Optional[bool]]
        self._consent_ts: Final[Optional[int]]
        self._consent_version: Final[Optional[int]]
        self._creation_ts: Final[int]
        self._deactivated: Final[bool]
        self._displayname: Final[Optional[str]]
        self._erased: Final[bool]
        self._external_ids: Final[List[ExternalID]]
        self._is_guest: Final[bool]
        self._locked: Final[bool]
        self._name: Final[str]
        self._shadow_banned: Final[bool]
        self._threepids: Final[List[ThreePID]]
        self._user_type: Final[str]

        try:
            response = homeserver.api_get(
                endpoints.USER_DETAILS.format(user_id=user_id)
            )
            self._name = response["name"]
            self._displayname = response["displayname"]
            self._threepids = []
            for three_pid in response["threepids"]:
                self._threepids.append(
                    ThreePID(
                        three_pid["medium"],
                        three_pid["address"],
                        three_pid["added_at"],
                        three_pid["validated_at"],
                    )
                )
            self._avatar_url = response["avatar_url"]
            self._is_guest = bool(response["is_guest"])
            self._admin = bool(response["admin"])
            self._deactivated = bool(response["deactivated"])
            self._erased = bool(response["erased"])
            self._shadow_banned = bool(response["shadow_banned"])
            self._creation_ts = response["creation_ts"]
            self._appservice_id = response["appservice_id"]
            self._consent_server_notice_sent = response["consent_server_notice_sent"]
            self._consent_version = response["consent_version"]
            self._consent_ts = response["consent_ts"]
            self._external_ids = []
            for external_id in response["external_ids"]:
                self._external_ids.append(
                    ExternalID(external_id["auth_provider"], external_id["external_id"])
                )
            self._user_type = response["user_type"]
            self._locked = response["locked"]
        except BadRequestError as e:
            if e.args[0]["error"] == "Can only look up local users":
                self._name = user_id
                self._threepids = []
                self._is_guest = True
                self._admin = False
                self._deactivated = False
                self._erased = False
                self._shadow_banned = False
                self._creation_ts = 0
                self._external_ids = []
                self._user_type = "Remote"
                self._locked = False

                self._appservice_id = None
                self._avatar_url = None
                self._consent_server_notice_sent = None
                self._consent_ts = None
                self._consent_version = None
                self._displayname = None
            else:
                raise e
        except EndpointNotFoundError:
            self._name = user_id
            self._threepids = []
            self._is_guest = False
            self._admin = False
            self._deactivated = True
            self._erased = True
            self._shadow_banned = True
            self._creation_ts = 0
            self._external_ids = []
            self._user_type = "Non-Existent"
            self._locked = True

            self._appservice_id = None
            self._avatar_url = None
            self._consent_server_notice_sent = None
            self._consent_ts = None
            self._consent_version = None
            self._displayname = None

    def __str__(self) -> str:
        if self._displayname is not None:
            return f"{self._displayname} ({self._name})"
        return f"{self._name}"

    @property
    def appservice_id(self) -> Optional[str]:
        """TODO: Confirm type and meaning"""
        return self._appservice_id

    @property
    def avatar_url(self) -> Optional[str]:
        """URL to user provided avatar"""
        return self._avatar_url

    @property
    def consent_server_notice_sent(self) -> Optional[bool]:
        """TODO: Confirm type and meaning"""
        return self._consent_server_notice_sent

    @property
    def consent_version(self) -> Optional[int]:
        """The version of the consent statement consented to"""
        return self._consent_version

    @property
    def consented(self) -> Optional[datetime]:
        """When the user consented"""
        if self._consent_ts is not None:
            return timestamp_ms_to_datetime(self._consent_ts)
        return None

    @property
    def created(self) -> datetime:
        """When the User was created."""
        return timestamp_ms_to_datetime(self._creation_ts)

    @property
    def display_name(self) -> Optional[str]:
        """User configured display name"""
        return self._displayname

    @property
    def experimental_features(self) -> Dict[str, bool]:
        """list which features are enabled/disabled for a given user

        Returns:
            Dict[str, bool]: A list of known experimental feature codes and their status
        """
        return self._homeserver.api_get(
            endpoints.EXPERIMENTAL_FEATURES.format(user_id=self.name)
        )["features"]

    @property
    def external_ids(self) -> List[ExternalID]:
        """External identities associated with the User"""
        return self._external_ids

    @property
    def is_admin(self) -> bool:
        """If the user is an admin"""
        return self._admin

    @property
    def is_active(self) -> bool:
        """If the user's account is active"""
        return not self._deactivated

    @property
    def is_erased(self) -> bool:
        """If the user's account has been erased"""
        return self._erased

    @property
    def is_guest(self) -> bool:
        """If the user is a guest"""
        return self._is_guest

    @property
    def is_locked(self) -> bool:
        """TODO: Confirm type and meaning"""
        return self._locked

    @property
    def is_shadow_banned(self) -> bool:
        """If the user's account is shadow banned"""
        return self._shadow_banned

    @property
    def name(self) -> str:
        """fully-qualified user id: for example, @user:server.com."""
        return self._name

    @property
    def third_party_ids(self) -> List[ThreePID]:
        """User added third-party identifiers"""
        return self._threepids

    @property
    def user_type(self) -> str:
        """TODO: Confirm type and meaning"""
        return self._user_type

    def disable_experimental_features(self, feature_code: str) -> bool:
        """Disables an experimental feature for a given user

        Returns:
            bool: If the feature was disabled.
        """
        try:
            self._homeserver.api_put(
                endpoints.EXPERIMENTAL_FEATURES.format(user_id=self.name),
                json={"features": {feature_code: False}},
            )
            return True
        except BadRequestError:
            return False

    def enable_experimental_features(self, feature_code: str) -> bool:
        """Enables an experimental feature for a given user

        Returns:
            bool: If the feature was enabled.
        """
        try:
            self._homeserver.api_put(
                endpoints.EXPERIMENTAL_FEATURES.format(user_id=self.name),
                json={"features": {feature_code: True}},
            )
            return True
        except BadRequestError:
            return False


def datetime_to_timestamp_ms(timestamp: datetime) -> int:
    """Convert a Python datetime object into a milliseconds since Epoch int.

    Args:
        timestamp (datetime): The timestamp to convert.

    Returns:
        int: The converted timestamp.
    """

    return int(timestamp.timestamp() * 1000)


def timestamp_ms_to_datetime(timestamp: int) -> datetime:
    """Convert a milliseconds since Epoch int to a Python datetime object.

    Args:
        timestamp (int): The timestamp to convert.

    Returns:
        datetime: The converted timestamp.
    """

    return datetime.fromtimestamp(timestamp / 1000.0)
