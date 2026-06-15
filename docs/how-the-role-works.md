# How the Role Works

The whole project is **one role, `proxmox_vm`, run once per VM** — the Windows DC and the ISE
node are built by the *same* tasks. `provision.yml` applies that role across the `enclave` hosts,
`serial: 1` so the DC finishes before ISE starts (ISE needs the DC's DNS at setup):

```yaml
- hosts: enclave
  connection: local      # all work is delegated to localhost / the PVE API
  serial: 1              # one host at a time → DC before ISE
  roles: [proxmox_vm]
```

Inside the role (`roles/proxmox_vm/tasks/main.yml`), per VM:

## 1. Disk + CD-ROM assembly
The disk is `{{ proxmox_storage }}:{{ disk_gb }},format=qcow2,ssd=1` on the bus from `vm_spec`
(`scsi0` for ISE, `sata0` for the DC). The install ISO is always mounted at `ide2`; **for Windows
only**, the answer ISO (`ide0`) and the virtio-win ISO (`ide1`) are added too — a single
`combine()` expression that simply omits them for ISE.

## 2. Windows answer ISO (DC only, `build_answer_iso: true`)
The three Jinja templates are rendered (`no_log` — they hold the Administrator + DSRM passwords),
copied to the PVE node, and packed into a **labelled** ISO:

```bash
genisoimage -quiet -o <name>-answer.iso -V WINANSWER -J -r /tmp/<name>-answer/
```

The label **`WINANSWER`** matters — the unattended install's `FirstLogonCommands` find the answer
files by volume label. `autounattend.xml` does the install, `setup-dc.ps1` promotes the forest,
and `phase2.ps1` fixes authoritative NTP + DNS + firewall (see
[Gotchas → Windows DC NTP](GOTCHAS.md#windows-dc-ntp-this-one-is-nasty)).

## 3. Create + start the VM
One `community.proxmox.proxmox_kvm` call builds either VM from `vm_spec` — `cpu: host`,
`numa: true`, `balloon: 0`, the disk on its bus, a single `net0` tagged onto
`enclave_bridge`/`enclave_vlan`, a `serial0` socket **only when `vm_spec.serial`** (ISE), and the
guest agent enabled only for Windows. A second call starts it.

## 4. Next steps
A final `debug` prints what to do by hand — for ISE, the **detach-the-ISO** command that avoids
the [auto-reinstall trap](GOTCHAS.md#the-installer-reboots-back-into-itself-auto-reinstall-trap);
for the DC, the `nslookup` that confirms the forest is serving DNS.

!!! note "One role, two VMs"
    Because the only per-VM input is `vm_spec`, the DC↔ISE difference is entirely data, not code.
    That is what makes adding a second DC or an ISE PSN a one-file change (see
    [Configuration → Add a node](configuration.md)).
