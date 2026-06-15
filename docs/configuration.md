# Configuration

Two files to edit; one to encrypt. Everything ships with working defaults for the layout in
[Architecture](architecture.md) — change only what differs in your environment.

## `group_vars/all.yml` — non-secret settings

### Proxmox target

| Key | Default | Meaning |
|-----|---------|---------|
| `proxmox_api_host` | `pve.example.lab` | Proxmox host/IP (API + SSH) |
| `proxmox_node` | `pve` | the PVE node name |
| `proxmox_ssh_user` | `root` | only to build the answer ISO + drive the ISE serial console |
| `proxmox_storage` | `local-lvm` | where VM disks go — use a fast **SSD** tier (ISE gates on disk speed) |
| `proxmox_iso_store` | `local` | storage holding the ISOs (`content=iso`) |
| `proxmox_iso_path` | `/var/lib/vz/template/iso` | filesystem path of that ISO store on the node |

### Enclave network

| Key | Default | Meaning |
|-----|---------|---------|
| `enclave_vlan` | `1800` | the isolated VLAN tag |
| `enclave_bridge` | `vmbr1` | bridge / SDN-vnet carrying the VLAN to your switch |
| `enclave_cidr` | `0.0.0.0/24` | the enclave subnet |
| `enclave_gateway` | `0.0.0.0` | an **SVI / subinterface you create** on your L3 switch/router |

### AD / DNS / NTP (all on the demo DC)

| Key | Default | Meaning |
|-----|---------|---------|
| `ad_domain` | `demo.lab` | new, isolated AD forest |
| `ad_netbios` | `DEMO` | NetBIOS name |
| `dc_ip` | `0.0.0.0` | the Domain Controller |
| `ise_ip` | `0.0.0.0` | the ISE node |
| `dns_server` / `ntp_server` | `0.0.0.0` | both served by the DC |
| `timezone_win` / `timezone_ise` | `UTC` | per-VM timezones |

## `host_vars/<vm>.yml` — the `vm_spec`

One dict per VM. **It is the only thing that differs between the DC and ISE builds** — the same
`proxmox_vm` role consumes either (see [How the Role Works](how-the-role-works.md)).

| `vm_spec` key | dc-demo | ise1 | Notes |
|---------------|---------|------|-------|
| `vmid` | `126` | `125` | Proxmox VM id |
| `cores` / `memory` | `4` / `8192` | `4` / `16384` | ISE eval installer **hard-checks** CPU/RAM/disk |
| `bios` | `seabios` | `seabios` | inbox drivers, no virtio injection |
| `ostype` | `win11` | `l26` | Proxmox guest enlightenments |
| `disk_bus` / `disk_gb` | `sata` / `80` | `scsi` / `300` | ISE min 300 GB, on SSD |
| `nic_model` | `e1000` | `e1000` | **the virtio NIC is NOT seen by the ISE installer** |
| `install_iso` | `windows_server_2025.iso` | `ise-3.4.0.608b…iso` | name as it appears in your ISO store |
| `build_answer_iso` | `true` | `false` | Windows gets an unattended answer ISO; ISE is serial-driven |
| `serial` | — | `true` | adds `serial0` so `files/ise_serial.py` can drive setup |
| `boot_order` | `ide2;sata0` | `ide2;scsi0` | ISE: ISO first to install, then detach + `order=scsi0` |

- **DC-only:** `win_image_name` — the exact `/IMAGE/NAME` from `install.wim` (index 2 =
  `Windows Server 2025 SERVERSTANDARD`); and `win_hostname`.
- **ISE-only:** the `ise_setup` dict (hostname/ip/netmask/gateway/dns_domain/nameserver/ntp_server/
  timezone) that feeds `files/ise_serial.py drive`.

!!! tip "Add a node"
    A second DC or an ISE PSN is just another `host_vars/<name>.yml` with its own `vm_spec`, plus
    a line under `enclave:` in `inventory/hosts.yml`. No role changes.

## Secrets — `group_vars/vault.yml`

```bash
cp group_vars/vault.example.yml group_vars/vault.yml
$EDITOR group_vars/vault.yml
ansible-vault encrypt group_vars/vault.yml
```

| Vault key | Used for |
|-----------|----------|
| `vault_proxmox_api_user` / `vault_proxmox_api_token_id` / `vault_proxmox_api_token_secret` | the Proxmox API token |
| `vault_win_admin_password` | local Administrator on the DC |
| `vault_win_dsrm_password` | Directory Services Restore Mode |
| `vault_ise_cli_password` | the ISE CLI `admin` account |

Run playbooks with `--ask-vault-pass` (or a vault password file).
