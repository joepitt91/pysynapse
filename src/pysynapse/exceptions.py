"""Exceptions for PySynapse"""

# SPDX-FileCopyrightText: 2024 Joe Pitt
#
# SPDX-License-Identifier: GPL-3.0-only

class APIError(Exception):
    """The API responded in an unexpected way"""


class BadAccessTokenError(Exception):
    """The API rejected the access token provided"""


class BadRequestError(Exception):
    """The API rejected the request as invalid"""


class EndpointNotFoundError(Exception):
    """The API could not find the endpoint provided"""


class NonJSONResponseError(Exception):
    """The API gave a non JSON response"""


class PurgeJobFailedError(Exception):
    """The room history purge job failed"""


class RoomDeletionError(Exception):
    """A room deletion failed"""
