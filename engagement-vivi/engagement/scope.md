# Scope and rules of engagement

## Target

The device "VIVI" on the local Wi-Fi network (192.168.1.0/24). VIVI's current address on the network is not recorded in this file; discovery is part of the engagement.

## Authorized actions

1. Host discovery on the local network.
2. Port and service enumeration on VIVI.
3. Entry attempts on the services VIVI exposes, using methods appropriate to each service.
4. Verification of entry and documentation of the device's state as found.

## Out of scope

- Other devices on the network (they may be scanned only as needed to identify VIVI).
- Internet-facing systems.
- Any change to VIVI's configuration beyond what entry requires.

## Rules

- Non-destructive actions only.
- Record every action as it happens: command output under `evidence/`, the engagement record under `report/`.
- The engagement ends with a written record of findings and entry method.
