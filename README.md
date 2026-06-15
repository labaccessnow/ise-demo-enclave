# ise-demo-enclave

Ansible to stand up a **self-contained Cisco ISE + Windows Server Active Directory
lab** on Proxmox VE, end to end:

* a **Windows Server 2025 Domain Controller** (new isolated forest, DNS + authoritative NTP), installed fully unattended;
* a **Cisco ISE 3.4** node that joins it;
* both on one isolated VLAN, provisioned by **one reusable role** (`proxmox_vm`) — the
  only difference between the two builds is a per-host `vm_spec`.

It exists because doing this by hand hides a pile of sharp edges (unattended Windows
answer files, the ISE installer's reboot-into-reinstall trap, Windows NTP refusing to
serve, driving the ISE serial setup wizard). Those are all encoded here. See
[`docs/GOTCHAS.md`](docs/GOTCHAS.md).

> ⚠️ Lab tool. It wipes/creates VMs and writes AD + NTP config. Run it against a lab
> Proxmox node, not production. No warranty.

## What it builds

```
              VLAN <enclave_vlan> / <enclave_cidr>   (isolated; nothing routes to prod)
  ┌─────────────────────────────┐      ┌─────────────────────────────┐
  │ dc-demo  (Win Server 2025)  │      │ ise1  (Cisco ISE 3.4)       │
  │ new forest demo.lab         │◄─────│ joins demo.lab              │
  │ DNS + authoritative NTP     │ dns  │ RADIUS / NAC                │
  │ 0.0.0.0                  │ ntp  │ 0.0.0.0                  │
  └─────────────────────────────┘      └─────────────────────────────┘
        gateway = your L3 switch/router SVI for the VLAN (0.0.0.0)
```

## Requirements

* Ansible 2.15+ on the control machine, plus the collections in `requirements.yml`:
  ```bash
  ansible-galaxy collection install -r requirements.yml
  ```
* A Proxmox VE node reachable by API, with an **API token** (Datacenter → Permissions → API Tokens).
* On the node's ISO storage: the **Windows Server 2025 ISO**, a **virtio-win ISO**
  (symlinked to `virtio-win.iso`), and the **Cisco ISE 3.4 ISO** (you supply these).
* `genisoimage` on the Proxmox node (used to build the Windows answer ISO).
* An L3 gateway for the VLAN (a switch SVI / router subinterface) at `enclave_gateway`.
* `sshpass`/SSH access to the node as root (only for the answer-ISO build + the ISE serial console).

## Configure

1. **Non-secret settings** — edit `group_vars/all.yml` (Proxmox host/node/storage, the
   VLAN bridge, the enclave subnet/gateway, the AD domain, ISO filenames).
2. **Per-VM specs** — `host_vars/dc-demo.yml` and `host_vars/ise1.yml` (vmid, cores, RAM,
   disk, NIC, etc.). To add nodes (a second DC, an ISE PSN) just drop another `host_vars`
   file with a `vm_spec` and add it to `inventory/hosts.yml`.
3. **Secrets** — copy and encrypt the vault:
   ```bash
   cp group_vars/vault.example.yml group_vars/vault.yml
   $EDITOR group_vars/vault.yml          # fill in real values
   ansible-vault encrypt group_vars/vault.yml
   ```

## Run

```bash
# 1) Windows DC first (ISE needs its DNS at setup). Unattended install + promotes the forest.
ansible-playbook provision.yml --limit dc-demo --ask-vault-pass
#    wait ~25 min; verify on the DC console:  nslookup ise1.demo.lab  -> 0.0.0.0

# 2) Cisco ISE — creates the VM and boots the installer.
ansible-playbook provision.yml --limit ise1 --ask-vault-pass
```

Then finish ISE (its first-boot `setup` wizard is interactive over serial — not
Ansible-automatable). A helper is provided:

```bash
# After the ISE OS install reboots, DETACH the install ISO or it re-enters the
# ISOLINUX menu with a 150-second auto-REINSTALL countdown:
ssh root@<pve> 'qm stop <ise_vmid>; qm set <ise_vmid> --delete ide2 --boot order=scsi0; qm start <ise_vmid>'

# Drive the setup wizard over the serial console:
export PVE_SSH=root@<pve> ISE_VMID=<ise_vmid> ISE_CLI_PASSWORD='...'
python3 files/ise_serial.py drive          # fills hostname/ip/dns/ntp/admin from host_vars + env
python3 files/ise_serial.py waitup         # nudge until the login prompt appears (~30-45 min)
python3 files/ise_serial.py appstatus      # log in + `show application status ise`
```

## Layout
```
provision.yml                     play the proxmox_vm role across the enclave hosts
inventory/hosts.yml               the two (or more) VMs
group_vars/all.yml                non-secret config (edit me)
group_vars/vault.example.yml      secret template -> copy to vault.yml + ansible-vault encrypt
host_vars/{dc-demo,ise1}.yml      per-VM vm_spec (the ONLY difference between the builds)
roles/proxmox_vm/                 creates either VM from vm_spec (community.proxmox.proxmox_kvm)
  templates/autounattend.xml.j2     Windows unattended install
  templates/setup-dc.ps1.j2         promote the forest
  templates/phase2.ps1.j2           authoritative NTP + DNS + firewall + ISE A/PTR
files/ise_serial.py               drive/watch the ISE serial console
docs/GOTCHAS.md                   the sharp edges, written down
```

## License
MIT — see [LICENSE](LICENSE).
