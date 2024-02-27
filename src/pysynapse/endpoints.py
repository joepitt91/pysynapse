"""Synapse admin API endpoints"""

# SPDX-FileCopyrightText: 2024 Joe Pitt
#
# SPDX-License-Identifier: GPL-3.0-only

from typing import Final


BACKGROUND_UPDATES_ENABLED: Final[str] = "_synapse/admin/v1/background_updates/enabled"
"""Checks if background updates are enabled on the homeserver.

    Method: GET

Enables or disables background updates on the homeserver.

    Method: POST
"""

BACKGROUND_UPDATES_RUN: Final[str] = "_synapse/admin/v1/background_updates/start_job"
"""Schedules a specific background update to run. The job starts immediately after calling the API.

    Method: POST
"""

BACKGROUND_UPDATES_STATUS: Final[str] = "_synapse/admin/v1/background_updates/status"
"""Gets the current status of the background updates.

    Method: GET
"""

DEVICE_DETAILS: Final[str] = "_synapse/admin/v2/users/{user_id}/devices/{device_id}"
"""Gets details of a user's device.

    Method: GET

    Args:
        user_id (str): Fully-qualified user id: for example, `@user:server.com`.
        device_id (str): Identifier of device.
"""

EVENT_CONTEXT: Final[str] = "_synapse/admin/v1/rooms/{room_id}/context/{event_id}"
"""Get the context about an event.

    Method: GET
            
    Args:
        room_id (str): The ID of the room the event was in.
        event_id (str): The ID of the event within the room.
"""

EVENT_REPORT_DELETE: Final[str] = "_synapse/admin/v1/event_reports/{report_id}"
"""Delete an event report.

    Method: DELETE
    
    Args:
        report_id (int): The ID of the event report.
"""

EVENT_REPORT_DETAILS: Final[str] = "_synapse/admin/v1/event_reports/{report_id}"
"""Gets details of reported events.

    Method: GET

    Args:
        report_id (int): The ID of the event report.
"""

EVENT_REPORTS: Final[str] = "_synapse/admin/v1/event_reports"
"""Gets details of reported events.

    Method: GET
"""

EXPERIMENTAL_FEATURES: Final[str] = "_synapse/admin/v1/experimental_features/{user_id}"
"""list which features are enabled/disabled for a given user

    Method: GET

    Args:
        user_id (str): The ID of the user.
    
Enable or Disable experimental features for a given user.

    Method: PUT

    Args:
        user_id (str): The ID of the user.
"""

MEDIA_DELETE: Final[str] = "_synapse/admin/v1/media/delete"
"""Delete media from the homeserver by last used time.

    Method: POST
"""

MEDIA_DOWNLOAD: Final[str] = "_matrix/media/v1/download/{server_name}/{media_id}"
"""Download a media item.

    Method: GET
    
    Args:
        server_name (str): The homeserver's server name.
        media_id (str): The media key to download.
"""

MEDIA_ITEM: Final[str] = "_synapse/admin/v1/media/{server_name}/{media_id}"
"""Delete media from the homeserver by ID.

    Method: DELETE

    Args:
        server_id (str): The name of your local server (e.g matrix.org).
        media_id (str): The ID of the media.
"""

MEDIA_PROTECT: Final[str] = "_synapse/admin/v1/media/protect/{media_id}"
"""Protects a piece of local media from being quarantined.

    Method: POST
"""

MEDIA_PURGE_CACHE: Final[str] = "_synapse/admin/v1/purge_media_cache"
"""Purges old cached remote media.

    Method: POST
"""

MEDIA_QUARANTINE: Final[str] = (
    "_synapse/admin/v1/media/quarantine/{server_name}/{media_id}"
)
"""Quarantines a piece of local or remote media.

    Method: POST

    Args:
        server_name (str): The source server.
        media_id (str): The ID of the media to quarantine.
"""

MEDIA_QUARANTINE_ROOM: Final[str] = "_synapse/admin/v1/room/{room_id}/media/quarantine"
"""Quarantines all local and remote media in a room.

    Method: POST

    Args:
        room_id (str): The ID of the target room.
"""

MEDIA_QUARANTINE_USER: Final[str] = "_synapse/admin/v1/user/{user_id}/media/quarantine"
"""Quarantines all local and remote media from a user.

    Method: POST

    Args:
        user_id (str): The ID of the target user.
"""

MEDIA_UNPROTECT: Final[str] = "_synapse/admin/v1/media/unprotect/{media_id}"
"""Remove protection of a piece of local media from being quarantined.

    Method: POST
"""

MEDIA_UNQUARANTINE: Final[str] = (
    "_synapse/admin/v1/media/unquarantine/{server_name}/{media_id}"
)
"""Releases a quarantined piece of local or remote media.

    Method: POST

    Args:
        server_name (str): The source server.
        media_id (str): The ID of the media to release from quarantine.
"""

REGISTER_USER: Final[str] = "_synapse/admin/v1/register"
"""Get a nonce to register a new user.

    Method: GET
    
Register a new user.

    Method: POST
"""

REGISTRATION_TOKEN: Final[str] = "_synapse/admin/v1/registration_tokens/{token}"
"""Get a named registration token.

    Method: GET

    Args:
        token (str): The token to get details of.

Update a named registration token.

    Method: PUT

    Args:
        token (str): The token to get details of.

Delete a named registration token.

    Method: DELETE

    Args:
        token (str): The token to get details of.
"""

REGISTRATION_TOKEN_CREATE: Final[str] = "_synapse/admin/v1/registration_tokens/new"
"""Create a new registration token.

    Method: POST
"""

REGISTRATION_TOKENS: Final[str] = "_synapse/admin/v1/registration_tokens"
"""Get all registration tokens.

    Method: GET
"""

RENEW_ACCOUNT: Final[str] = "_synapse/admin/v1/account_validity/validity"
"""Extends the validity of an account.

    Method: POST
"""

ROOM_BLOCK: Final[str] = "_synapse/admin/v1/rooms/{room_id}/block"
"""Check if a room is blocked, and if so by who.

    Method: GET
    
    Args:
        room_id (str): The ID of the room.

Block or unblock a room.

    Method: PUT
    
    Args:
        room_id (str): The ID of the room.
"""

ROOM_DELETE: Final[str] = "_synapse/admin/v2/rooms/{room_id}"
"""Delete a room.

    Method: DELETE

    Args:
        room_id (str): The ID of the room.
"""

ROOM_DELETE_STATUS: Final[str] = "_synapse/admin/v2/rooms/delete_status/{delete_id}"
"""Check if a room has finished deleting.

    Method: GET
    
    Args:
        delete_id (str): The ID of the delete to check.
"""

ROOM_DETAILS: Final[str] = "_synapse/admin/v1/rooms/{room_id}"
"""Gets details of a room.

    Method: GET

    Args:
        room_id (str): The ID of the room.
"""

ROOM_INVITE_USER: Final[str] = "_synapse/admin/v1/join/{room_id}"
"""Invite a user to a room.

    Method: GET
    
    Args:
        room_id (str): The room to add the user to."""

ROOM_LIST: Final[str] = "_synapse/admin/v1/rooms"
"""Get a list of all rooms on the homeserver.

    Method: GET"""

ROOM_MAKE_ADMIN: Final[str] = "_synapse/admin/v1/rooms/{room_id}/make_room_admin"
"""Make a user an admin within a room.

    Method: POST
    
    Args:
        room_id (str): The ID of the room.
"""

ROOM_MEMBERS: Final[str] = "_synapse/admin/v1/rooms/{room_id}/members"
"""Gets a list of members of a room.

    Method: GET

    Args:
        room_id (str): The ID of the room.
"""

ROOM_MESSAGE_BY_TIMESTAMP: Final[str] = (
    "_synapse/admin/v1/rooms/{room_id}/timestamp_to_event"
)
"""Gets the ID of the nearest message in a room to the given timestamp.

    Method: GET

    Args:
        room_id (str): The ID of the room.
"""

ROOM_MESSAGES: Final[str] = "_synapse/admin/v1/rooms/{room_id}/messages"
"""Gets a list of messages in a room.

    Method: GET

    Args:
        room_id (str): The ID of the room.
"""

ROOM_PURGE_HISTORY: Final[str] = "_synapse/admin/v1/purge_history/{room_id}"
"""Purge historic events from their database.

    Method: POST
    
    Args:
        room_id (str): The room to purge history from.
"""

ROOM_PURGE_HISTORY_STATUS: Final[str] = (
    "_synapse/admin/v1/purge_history_status/{purge_id}"
)
"""Get the status of a room history purge.

    Method: GET
    
    Args:
        purge_id (str): The ID of the purge job to check
"""

ROOM_STATE: Final[str] = "_synapse/admin/v1/rooms/{room_id}/state"
"""Get all state messages from a room.

    Method: GET

    Args:
        room_id (str): The room ID.
"""

ROOMS: Final[str] = "_synapse/admin/v1/rooms"
"""Gets all rooms on the server.

    Method: GET
"""

SERVER_NOTICE: Final[str] = "_synapse/admin/v1/send_server_notice"
"""Sends a server notice to a user.

    Method: POST
"""

SERVER_KEYS: Final[str] = "_matrix/key/v2/server"
"""Get the homeserver's current and previous keys.

    Method: GET
"""

SERVER_VERSION: Final[str] = "_synapse/admin/v1/server_version"
"""Gets the current server version.

    Method: GET
"""

USER_DETAILS: Final[str] = "_synapse/admin/v2/users/{user_id}"
"""Gets details about a user.

    Method: GET
     
    Args:
        user_id (str): Fully-qualified user id: for example, `@user:server.com`.
"""

USER_MEDIA: Final[str] = "_synapse/admin/v1/users/{user_id}/media"
"""Gets a list of all local media that a specific user_id has created.

    Method: GET
    
    Args:
        user_id (str): The ID of the user.

Deletes all local media that a specific user_id has created.

    Method: DELETE
    
    Args:
        user_id (str): The ID of the user.
"""
