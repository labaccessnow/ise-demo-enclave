#!/usr/bin/env python3
"""Watch / drive a Cisco ISE VM's serial console over Proxmox `qm terminal`.

ISE's first-boot `setup` wizard is interactive and can't be done by Ansible — this
drives it (and watches the long app-init) over the serial socket via SSH to the node.

Config via environment:
  PVE_SSH           ssh target for the Proxmox node      (default root@pve)
  ISE_VMID          the ISE VM id                         (default 125)
  ISE_CLI_USER      ISE admin username                    (default admin)
  ISE_CLI_PASSWORD  ISE admin password                    (required for drive/appstatus)
  ISE_HOSTNAME / ISE_IP / ISE_NETMASK / ISE_GW / ISE_DNS_DOMAIN /
  ISE_NS / ISE_NTP / ISE_TZ   setup-wizard answers (defaults match the example enclave)

Modes:
  watch [seconds]   passive: print serial output for N sec (default 20)
  send  "<text>"    send text + Enter once
  drive [maxsec]    run the ISE setup wizard end-to-end
  waitup [maxsec]   nudge until the login prompt appears, then exit
  appstatus         log in + `show application status ise` (+ ntp/clock)

Requires: pexpect  (pip install pexpect)
"""
import os, sys, time, re
import pexpect

PVE = os.environ.get("PVE_SSH", "root@pve")
VMID = os.environ.get("ISE_VMID", "125")
CMD = f"ssh -tt -o BatchMode=yes -o StrictHostKeyChecking=accept-new {PVE} qm terminal {VMID} --iface serial0"

A = {  # setup-wizard answers (env-overridable)
    "hostname":   os.environ.get("ISE_HOSTNAME", "ise1"),
    "ip":         os.environ.get("ISE_IP", "0.0.0.0"),
    "netmask":    os.environ.get("ISE_NETMASK", "255.255.255.0"),
    "gateway":    os.environ.get("ISE_GW", "0.0.0.0"),
    "dns_domain": os.environ.get("ISE_DNS_DOMAIN", "demo.lab"),
    "nameserver": os.environ.get("ISE_NS", "0.0.0.0"),
    "ntp":        os.environ.get("ISE_NTP", "0.0.0.0"),
    "timezone":   os.environ.get("ISE_TZ", "UTC"),
}
ISE_USER = os.environ.get("ISE_CLI_USER", "admin")
ISE_PW = os.environ.get("ISE_CLI_PASSWORD", "")


def connect(timeout):
    return pexpect.spawn(CMD, timeout=timeout, encoding="utf-8", codec_errors="ignore")


def read_idle(p, idle=1.8, cap=20):
    buf, start = "", time.time()
    while time.time() - start < cap:
        try:
            buf += p.read_nonblocking(4096, timeout=idle)
        except pexpect.TIMEOUT:
            if buf.strip():
                break
        except pexpect.EOF:
            break
    return buf


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "watch"

    if mode == "watch":
        dur = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        p = connect(dur + 20)
        buf, end = "", time.time() + dur
        while time.time() < end:
            try: buf += p.read_nonblocking(8192, timeout=2)
            except pexpect.TIMEOUT: pass
            except pexpect.EOF: break
        print(buf[-6000:] if buf else "(no serial output this window)")

    elif mode == "send":
        p = connect(20); time.sleep(1)
        p.send(sys.argv[2] + "\r"); time.sleep(2)
        try: print(p.read_nonblocking(8192, timeout=3)[-3000:])
        except Exception: pass

    elif mode == "waitup":
        maxsec = int(sys.argv[2]) if len(sys.argv) > 2 else 1800
        p = connect(maxsec + 30); end = time.time() + maxsec
        while time.time() < end:
            try: p.send("\r")
            except Exception: break
            buf = read_idle(p, idle=1.5, cap=6)
            if buf and re.search(r"login:|/admin#|/admin>", buf, re.I):
                print("ISE PROMPT DETECTED:\n" + buf[-400:]); return
            time.sleep(18)
        print("waitup timeout — still initializing or stuck")

    elif mode == "drive":
        if not ISE_PW: sys.exit("set ISE_CLI_PASSWORD")
        maxsec = int(sys.argv[2]) if len(sys.argv) > 2 else 900
        rules = [
            (["re-enter", "password"], ISE_PW, "pw-confirm"),
            (["enter", "password"], ISE_PW, "pw"),
            (["password:"], ISE_PW, "pw"),
            (["login:"], "setup", "login"),
            (["ipv6"], "N", "ipv6"),
            (["another", "name server"], "N", "more-ns"),
            (["another", "nameserver"], "N", "more-ns"),
            (["add", "nameserver"], "N", "more-ns"),
            (["secondary", "ntp"], "N", "more-ntp"),
            (["another", "ntp"], "N", "more-ntp"),
            (["hostname"], A["hostname"], "hostname"),
            (["ip address"], A["ip"], "ip"),
            (["netmask"], A["netmask"], "netmask"),
            (["default gateway"], A["gateway"], "gw"),
            (["gateway"], A["gateway"], "gw"),
            (["dns domain"], A["dns_domain"], "domain"),
            (["domain"], A["dns_domain"], "domain"),
            (["primary nameserver"], A["nameserver"], "ns"),
            (["nameserver"], A["nameserver"], "ns"),
            (["ntp server"], A["ntp"], "ntp"),
            (["timezone"], A["timezone"], "tz"),
            (["ssh"], "Y", "ssh"),
            (["username"], ISE_USER, "username"),
            (["continue"], "Y", "continue"),
        ]
        p = connect(maxsec + 30); end = time.time() + maxsec
        drain = None
        while time.time() < end:
            buf = read_idle(p)
            if not buf.strip():
                if drain and time.time() > drain: break
                continue
            if drain:
                if time.time() > drain: break
                continue
            tail = buf[-500:].lower()
            if not tail.rstrip().endswith((":", "?", "]")):   # only act on a waiting prompt
                continue
            for kws, resp, name in rules:
                if all(k in tail for k in kws):
                    print(f">> {name}: send {'****' if 'pw' in name else resp!r}")
                    p.send(resp + "\r")
                    if name == "pw-confirm": drain = time.time() + 90
                    time.sleep(0.6)
                    break
            else:
                print("UNKNOWN PROMPT — stopping:\n" + buf[-600:]); break

    elif mode == "appstatus":
        if not ISE_PW: sys.exit("set ISE_CLI_PASSWORD")
        p = connect(200); p.send("\r")
        i = p.expect([r"login:", r"/admin#", r"/admin>", pexpect.TIMEOUT], timeout=20)
        if i == 0:
            p.sendline(ISE_USER)
            p.expect([r"[Pp]assword:"], timeout=15)
            p.sendline(ISE_PW)
            if p.expect([r"/admin#", r"/admin>", r"[Ii]ncorrect", pexpect.TIMEOUT], timeout=30) >= 2:
                sys.exit("login failed")
        p.sendline("terminal length 0")
        p.expect([r"/admin#", pexpect.TIMEOUT], timeout=10)
        for cmd in ["show application status ise", "show ntp", "show clock"]:
            p.sendline(cmd); time.sleep(2)
            print(f"\n===== {cmd} =====\n{read_idle(p, idle=2.0, cap=50).strip()}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
