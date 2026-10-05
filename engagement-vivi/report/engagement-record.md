# Engagement record — device entry: "VIVI"

- **Date:** 2026-10-04
- **Operator / network owner:** N. Hu
- **Authorization:** Network owner, per `engagement/letter.md` and `engagement/scope.md`. Local Wi-Fi network only; single target "VIVI"; non-destructive actions only.
- **Scope:** `192.168.1.0/24` (local Wi-Fi). Other hosts touched only as needed to identify VIVI.
- **Deliverable:** this record, from command output captured under `evidence/`.

This document is a write-up of evidence already collected. No network actions were performed in producing it.

---

## 1. Environment

Source: `evidence/00-environment.txt`

| Item | Value |
|------|-------|
| Capture time | Sun Oct 4 18:50:32 EDT 2026 |
| Operator host IP | 192.168.1.169 (interface `en0`) |
| Gateway | 192.168.1.1 |
| Scope network | 192.168.1.0/24 |
| Platform | macOS |
| Tools available | `arp`, `ping`, `dns-sd`, `nc`, `ssh`, `curl` (`nmap` not installed) |

The operator worked from a macOS laptop on the same Layer-2 Wi-Fi segment as the target. Discovery and enumeration were done with built-in tooling; port scanning was done with `nc` connect attempts rather than `nmap`.

---

## 2. Target identification

VIVI's address was not recorded in scope and had to be discovered.

**Name resolution (mDNS).** Source: `evidence/04-vivi-mdns-address.txt`

```
18:51:31.167  Add  40000002  18  Vivi.local.  192.168.1.171  60
```

`Vivi.local.` resolves via multicast DNS to **192.168.1.171** (record TTL 60s).

**Layer-2 confirmation (ARP).** Source: `evidence/01-arp-table.txt`

```
? (192.168.1.171) at 74:86:e2:0:aa:35 on en0 ifscope [ethernet]
```

The ARP table has a *resolved* entry for 192.168.1.171 — MAC `74:86:e2:00:aa:35` (OUI `74:86:E2`). A resolved ARP entry means the device answered an ARP request and is present on the local segment. 192.168.1.171 was one of only a handful of addresses in the /24 with a completed ARP entry; the large majority were `(incomplete)`.

**Conclusion:** VIVI = `Vivi.local` = **192.168.1.171**, MAC `74:86:e2:00:aa:35`, confirmed live at Layer 2.

---

## 3. Services VIVI advertises

Two mDNS service enumerations were captured.

**Service-type enumeration (network-wide).** Sources: `evidence/02-mdns-services.txt`, `evidence/08-mdns-services-long.txt`

Browsing `_services._dns-sd._udp.local` lists the service *types* present on the segment (not attributed to a specific host):

```
_amzn-wplay    _dosvc      _googlecast   _continuity   _asquic
_androidtvremote2   _nvstream_dbd   _companion-link   _ssh
_sftp-ssh   _rfb   _net-assistant   _airplay   _raop
```

**Instance resolution.** Source: `evidence/06-mdns-browse-services.txt`

Browsing the individual service types that returned instances resolved them to the operator's own machine:

- `_airplay._tcp` → *Niel's MacBook Pro*
- `_raop._tcp` → *620A50F9FA88@Niel's MacBook Pro*
- `_companion-link._tcp` → *Niel's MacBook Pro*

Browses for `_ssh`, `_sftp-ssh`, `_rfb`, `_googlecast`, and `_androidtvremote2` returned **no instances** within the capture window.

**Assessment of VIVI's advertised services:** The service-type list is a segment-wide view and cannot by itself be attributed to VIVI. In the captured output, **no service instance resolved to VIVI (192.168.1.171)** — every instance that resolved belonged to the operator's MacBook Pro. So while `Vivi.local` advertises an address record over mDNS, this evidence does **not** positively tie any advertised service (SSH, AirPlay, screen-sharing, cast, etc.) to VIVI. Either VIVI was not advertising service records during the capture, or its advertisements were not observed in these windows.

---

## 4. Port scan results

Two connect-scan passes were run against 192.168.1.171 with `nc`.

**Broad pass.** Source: `evidence/05-portscan-nc.txt` — 45 TCP ports attempted:

```
21 22 23 25 53 80 88 110 135 139 143 443 445 515 548 554 587
631 993 995 1883 3000 3306 3389 5000 5060 5555 5900 5901 6379
7000 8000 8008 8009 8080 8081 8083 8123 8443 8888 9000 9090 9100
49152 62078
```

**Result: every port returned `Operation timed out`.** No port produced a connection or a refusal.

**Focused re-check.** Source: `evidence/07-portscan-slow.txt` — ports 22 and 80, run slower:

```
nc: connectx to 192.168.1.171 port 22 (tcp) failed: Operation timed out
nc: connectx to 192.168.1.171 port 80 (tcp) failed: Operation timed out
```

Same result — both timed out.

**Interpretation:** All probes *timed out* rather than returning connection-refused (RST). Timeouts across the board indicate packets are being **dropped/filtered**, not actively rejected — the signature of a host firewall in stealth mode (or an upstream filter), as opposed to a host with simply-closed ports.

**ICMP.** Source: `evidence/03-resolve-vivi.txt` — `ping vivi.local (192.168.1.171)`: 2 attempts, **100% packet loss**. VIVI does not answer ICMP echo either.

---

## 5. Entry assessment

**Reachability summary for VIVI (192.168.1.171):**

| Layer | Result |
|-------|--------|
| L2 (ARP) | Reachable — ARP resolved to `74:86:e2:00:aa:35` |
| L3 (ICMP) | No response — 100% ping loss |
| L4 (TCP) | All 45 scanned ports filtered (timeout, no RST) |
| mDNS | Address record resolves; no service instance attributed to VIVI |

**Entry attempted:** None was possible. Entry attempts under the scope require a reachable service, and the enumeration found no open/reachable port and no service instance bound to VIVI. There was no listening endpoint to authenticate against, so no SSH, web, or other entry attempt could be initiated.

**Most likely explanation (in order):**

1. **Host firewall / stealth mode** — The device is present at L2 (ARP resolves) but silently drops ICMP and all TCP SYNs. This is the classic pattern of an OS firewall configured to not respond to probes. Most consistent with the evidence.
2. **Device asleep / powered down after advertising** — The mDNS address record (TTL 60s) and ARP entry may be recent cache from when the device was last awake; the device may have since gone to sleep or dropped off, which would also yield timeouts. The resolved (not incomplete) ARP entry argues for it having been present very recently.
3. **AP client isolation** — Less likely, since client isolation typically also blocks the ARP resolution that succeeded here.

**Bottom line:** VIVI was positively identified and located (`Vivi.local` → 192.168.1.171, MAC `74:86:e2:00:aa:35`) and confirmed live at Layer 2, but it is **not reachable at the network/transport layer**: it ignores ICMP and every scanned TCP port is filtered. No exposed service was found, so **entry could not be achieved or attempted** with the current state of the target.

**Recommended next steps (not performed — would require further network actions, outside this documentation-only task):**

- Re-run discovery while the device is known to be awake/active (e.g., immediately after a user interaction with it), since a stale-cache scenario would then present open services.
- If a host firewall is suspected, entry via the network alone will not succeed; local/physical access to the device or an out-of-band management/recovery path (vendor app, factory reset to restore owner access) is the realistic route to "restore access" as the letter requests.
- Confirm the vendor from OUI `74:86:E2` and consult that vendor's documented recovery procedure for the device.

---

## Evidence index

| File | Contents |
|------|----------|
| `evidence/00-environment.txt` | Operator host, gateway, scope, available tools |
| `evidence/01-arp-table.txt` | ARP table for 192.168.1.0/24 (VIVI at .171) |
| `evidence/02-mdns-services.txt` | mDNS service-type enumeration (network-wide) |
| `evidence/03-resolve-vivi.txt` | `ping vivi.local` — 100% loss |
| `evidence/04-vivi-mdns-address.txt` | mDNS resolve `Vivi.local` → 192.168.1.171 |
| `evidence/05-portscan-nc.txt` | `nc` scan, 45 ports — all timed out |
| `evidence/06-mdns-browse-services.txt` | mDNS instance resolution (only MacBook Pro) |
| `evidence/07-portscan-slow.txt` | `nc` re-check of 22/80 — timed out |
| `evidence/08-mdns-services-long.txt` | Second mDNS service-type enumeration |
