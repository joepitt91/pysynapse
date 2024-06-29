<!--
SPDX-FileCopyrightText: 2024 Joe Pitt

SPDX-License-Identifier: GPL-3.0-only
-->
# PySynapse

[![Pylint](https://github.com/joepitt91/pysynapse/actions/workflows/pylint.yml/badge.svg)](https://github.com/joepitt91/pysynapse/actions/workflows/pylint.yml)
[![CodeQL](https://github.com/joepitt91/pysynapse/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/joepitt91/pysynapse/actions/workflows/github-code-scanning/codeql)
[![CodeFactor](https://www.codefactor.io/repository/github/joepitt91/pysynapse/badge)](https://www.codefactor.io/repository/github/joepitt91/pysynapse)

Python Synapse (Matrix) server admin API module.

**NOTE:** This is my first time writing a Python module, its probably not perfect.

## Requirements

* Python3 (written on 3.11)
* requests
* validators

## Usage Examples

### Create a connection from a config file

```python
from configparser import ConfigParser
from os.path import abspath, dirname, join

try:
    from pysynapse import Homeserver
except ImportError:
    print("pysynapse not installed, install with:")
    print("python3 -m pip install pysynapse")
    exit(1)

config = ConfigParser()
config_file = join(dirname(abspath(__file__)), "config.ini")
if len(config.read(config_file)) != 1:
    print("Failed to load config.ini")
    exit(1)

homeserver = Homeserver(
    config.get("homeserver", "access_token"),
    config.get("homeserver", "host", fallback="localhost"),
    config.getint("homeserver", "port", fallback=8008),
    config.getboolean("homeserver", "secure", fallback=False),
    config.getboolean("homeserver", "verify", fallback=None),
    config.get("homeserver", "notices_user", fallback=None),
)

print(f"Connected to {homeserver.base_url} (Synapse {homeserver.server_version})")

```

### Print summary of event reports

```python

print(
    "| ID   | Reported            | Claimant                       | Defendant                      | Room                           |"
)
print(
    "|------|---------------------|--------------------------------|--------------------------------|--------------------------------|"
)

for event_report in homeserver.event_reports:
    print(
        "| {:4.4} | {:19.19} | {:30.30} | {:30.30} | {:30.30} |".format(
            str(event_report.id),
            str(event_report.received),
            str(event_report.user),
            str(event_report.sender),
            str(event_report.room),
        )
    )
```

### Purge forgotten rooms

```python
for room in homeserver.rooms:
    if room.forgotten:
        print("Deleting forgotten room: {}".format(room))
        room.delete(block_rejoining=False)
    else:
        print("Keeping room: {}".format(room))
        for member in room.members:
            print("- {}".format(member))
```
