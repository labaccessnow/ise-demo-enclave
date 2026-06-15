# Architecture

## The enclave

Everything lives on **one isolated VLAN** (`enclave_vlan`, default **1800** → `0.0.0.0/24`).
Routing to production is intentionally **not** required — the two VMs talk to each other on the
shared subnet, and the only external dependency is an L3 gateway you create for the VLAN.

```mermaid
flowchart TB
    subgraph vlan["VLAN 1800 · 0.0.0.0/24 — isolated enclave"]
        DC["<b>dc-demo</b> · 0.0.0.0<br/>Windows Server 2025<br/>forest <b>demo.lab</b><br/>DNS (authoritative)<br/>NTP (stratum-1, local clock)"]
        ISE["<b>ise1</b> · 0.0.0.0<br/>Cisco ISE 3.4<br/>joins demo.lab<br/>RADIUS / NAC"]
        ISE -->|"DNS lookups · NTP sync"| DC
    end
    GW["L3 gateway / SVI · 0.0.0.0<br/>(you create on your switch/router)"]
    GW --- vlan
    MGMT["your management net"] -. "route to enclave_cidr<br/>+ firewall allow (separate)" .-> GW
```

## DNS + NTP flow

The DC is the **single source of truth** for both:

- **DNS** — `demo.lab` is an AD-integrated forest; ISE points its nameserver at `0.0.0.0` during
  setup, which is exactly why the **DC is built first**.
- **NTP** — a freshly-promoted DC is *unsynchronized* and ISE refuses it, so the DC is made an
  **authoritative stratum-1 server off its own clock**. The full story (and the `w32tm` trap) is in
  [Gotchas → Windows DC NTP](GOTCHAS.md#windows-dc-ntp-this-one-is-nasty).

## Reaching the ISE admin GUI from another VLAN

The enclave is isolated by design. To reach ISE's admin GUI from a management network, your L3
device must **route to `enclave_cidr`** and your firewall must permit it — deliberately **outside**
this build. Within the enclave, ISE ↔ DC works with no routing.
