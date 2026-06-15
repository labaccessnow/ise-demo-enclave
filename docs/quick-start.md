# Quick Start

## Requirements

- **Ansible 2.15+** on the control machine, plus the collections in `requirements.yml`:
  ```bash
  ansible-galaxy collection install -r requirements.yml
  ```
- A **Proxmox VE** node reachable by API, with an **API token**
  (Datacenter → Permissions → API Tokens).
- On the node's ISO storage: the **Windows Server 2025 ISO**, a **virtio-win ISO** (symlinked to
  `virtio-win.iso`), and the **Cisco ISE 3.4 ISO** — you supply these.
- **`genisoimage`** on the Proxmox node (builds the Windows answer ISO).
- An **L3 gateway** for the VLAN (a switch SVI / router subinterface) at `enclave_gateway`.
- `sshpass` / SSH access to the node as root (only for the answer-ISO build + the ISE serial console).

## Configure

The full list is in **[Configuration](configuration.md)**. The short version:

```bash
# 1) non-secret settings
$EDITOR group_vars/all.yml      # Proxmox host/node/storage, VLAN, subnet, AD domain, ISO names
# 2) per-VM specs (sane defaults shipped)
$EDITOR host_vars/dc-demo.yml host_vars/ise1.yml
# 3) secrets
cp group_vars/vault.example.yml group_vars/vault.yml
$EDITOR group_vars/vault.yml
ansible-vault encrypt group_vars/vault.yml
```

## Run

Build the **DC first** — ISE needs its DNS at setup.

```bash
# 1) Windows DC — unattended install + promotes the forest (~25 min)
ansible-playbook provision.yml --limit dc-demo --ask-vault-pass
#    verify on the DC console:  nslookup ise1.demo.lab  ->  0.0.0.0

# 2) Cisco ISE — creates the VM and boots the installer
ansible-playbook provision.yml --limit ise1 --ask-vault-pass
```

Then finish ISE — its first-boot `setup` wizard is interactive over serial (not
Ansible-automatable). A helper drives it:

!!! danger "Detach the ISO or ISE auto-reinstalls"
    After the ISE OS install reboots, **detach the install ISO** or the VM re-enters the
    ISOLINUX menu with a ~150-second auto-**REINSTALL** countdown that wipes what you just
    installed. See [Gotchas](GOTCHAS.md#the-installer-reboots-back-into-itself-auto-reinstall-trap).

```bash
# detach the install ISO, boot from disk
ssh root@<pve> 'qm stop <ise_vmid>; qm set <ise_vmid> --delete ide2 --boot order=scsi0; qm start <ise_vmid>'

# drive the setup wizard over serial
export PVE_SSH=root@<pve> ISE_VMID=<ise_vmid> ISE_CLI_PASSWORD='...'
python3 files/ise_serial.py drive       # fills hostname/ip/dns/ntp/admin from host_vars + env
python3 files/ise_serial.py waitup      # nudge until the login prompt (~30–45 min)
python3 files/ise_serial.py appstatus   # log in + `show application status ise`
```
