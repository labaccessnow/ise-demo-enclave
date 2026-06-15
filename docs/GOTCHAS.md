# GOTCHAS — the sharp edges, written down

Everything below was hit building this for real. Each one will silently waste 20+
minutes if you don't know it.

## Cisco ISE

### The installer reboots back into itself (auto-reinstall trap)
After ISE lays down the OS it **reboots**. If the install ISO is still attached and
first in the boot order, the VM boots the ISO again and lands in the **ISOLINUX menu
with a ~150-second countdown that auto-starts a fresh REINSTALL** — wiping what you
just installed. As soon as the first install phase finishes, detach the ISO and boot
from disk:
```bash
qm stop <ise_vmid>
qm set <ise_vmid> --delete ide2 --boot order=scsi0
qm start <ise_vmid>
```

### Drive setup over serial, not the GUI
At the ISE boot menu pick **[2] Cisco ISE Installation (Serial Console)**. Then the
first-boot `setup` wizard runs on `ttyS0` and you can drive it with `files/ise_serial.py`.
Prompt order: hostname → ip → netmask → gateway → **IPv6? (N)** → DNS domain →
nameserver → add another? (N) → NTP → add another? (N) → timezone → SSH (Y) →
username → password → password again. Then it runs gateway/DNS pings + a disk I/O
test, then an NTP sync.

### NIC = e1000, not virtio
The ISE installer does **not** detect the Proxmox virtio NIC — the setup wizard shows
no interface. Use `e1000` (or vmxnet3). virtio-scsi for the disk is fine.

### Eval installer hard-checks resources
ISE 3.4 aborts if the VM is under-spec: it verifies CPU cores, clock, RAM, and disk,
and requires disk **write ≥ 50 MB/s, read ≥ 300 MB/s**. Put the disk on SSD. Minimum
eval profile: 4 vCPU / 16 GB / 300 GB.

### First boot is long and silent
After setup, ISE does "Installing Applications" + DB/cert init. The console is **silent
for 30–45 minutes**. It is not hung — check the hypervisor: high CPU / near-full RAM /
heavy disk I/O means it's working. `files/ise_serial.py waitup` nudges until the login
prompt appears.

## Windows DC NTP (this one is nasty)

A freshly-promoted DC with no upstream time source announces itself as
**unsynchronized (LeapIndicator = 3)**, and NTP clients — including ISE — **reject it**,
so ISE's setup NTP sync fails ("Incorrect time could render the system unusable").

The fix is to make the DC an **authoritative server off its own local clock**:
```powershell
w32tm /config /syncfromflags:NO /reliable:yes /update   # Type=NoSync + reliable
reg add "HKLM\SYSTEM\CurrentControlSet\Services\W32Time\Config" /v AnnounceFlags /t REG_DWORD /d 5 /f
reg add "HKLM\SYSTEM\CurrentControlSet\Services\W32Time\TimeProviders\NtpServer" /v Enabled /t REG_DWORD /d 1 /f
Restart-Service w32time
New-NetFirewallRule -DisplayName NTP-In -Direction Inbound -Protocol UDP -LocalPort 123 -Action Allow
w32tm /query /status   # expect: Leap Indicator 0(no warning), Stratum 1, Source: Local CMOS Clock
```
**Do NOT** use `w32tm /config /manualpeerlist:"127.127.1.0"` — that's Unix ntpd
reference-clock syntax, invalid for `w32tm`; it points the DC at a peer that doesn't
exist and it stays unsynchronized. (`phase2.ps1.j2` does the correct config; also note
the DC's Windows Firewall blocks inbound UDP 123 by default.)

If you just want to get past it during the build, answer **N** to ISE's NTP-retry — the
VM's clock is already correct from the host RTC — then fix the DC and ISE re-syncs on
its next poll.

## Windows unattended install

* **Edition name** in `host_vars` must match `install.wim` exactly. List them:
  `wiminfo <iso>/sources/install.wim` (or `dism /Get-WimInfo /WimFile:...`). Index 2 is
  usually "Windows Server 2025 SERVERSTANDARD" (Standard, Desktop Experience).
* **seabios + SATA disk + e1000 NIC** = all native Windows inbox drivers, so the
  unattended install needs no virtio driver injection.
* The answer ISO must be labelled **`WINANSWER`** (the FirstLogonCommands find it by
  label) and contain `autounattend.xml` at the root.

## Hypervisor headless access (no guest agent)

Installing only `qemu-ga` is not enough on Windows — the agent needs the **virtio-serial
driver** to reach the host, which the native-driver install doesn't include, so
`qm agent` won't work. To drive/verify a GUI Windows VM headless, use QEMU
`screendump` (framebuffer → image) and `sendkey` (keystroke injection) over `qm monitor`.

## Networking

The enclave is intentionally isolated. To reach the ISE **admin GUI from another VLAN**
(e.g. a management net), your L3 device must route to `enclave_cidr` and your firewall
must permit it — that's separate from this build. Within the enclave, ISE↔DC works on
the shared subnet with no routing.
