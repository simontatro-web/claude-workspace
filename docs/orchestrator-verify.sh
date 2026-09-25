#!/bin/bash
# Read-only checks V1-V20 from docs/orchestrator-research.md section 7.
# Starts, stops, installs and edits nothing. Secrets are redacted.
R() { sed -E -e 's/((key|token|secret|passw)[^=:]*[=:][[:space:]]*)[^[:space:]]+/\1<REDACTED>/Ig' -e 's/(bearer[[:space:]]+)[^[:space:]]+/\1<REDACTED>/Ig'; }
h() { echo; echo "===== $1 ====="; }
h "V0 time"; date -u; TZ=America/Chicago date
h "V1 users and sudo"; id simon; getent group sudo docker; sudo -l -U simon 2>&1 | R
h "V2 listening sockets"; sudo ss -ltnp
h "V3 units"; systemctl list-units --all 'jarvis*' 'llama*' 'bench*' --no-pager
systemctl cat llama-server jarvis-run-host-commands --no-pager 2>&1 | R
h "V4 production protection"; systemctl show llama-server -p OOMScoreAdjust -p MemoryMax -p Restart
h "V5 disk and memory"; df -h / /mnt/models; free -g
h "V6 small models on drive"; ls /mnt/models/models/slots /mnt/models/models/embed /mnt/models/models/verify /mnt/models/models/audio 2>&1 | head -80
h "V7 gate/voice/dataset files"; find /mnt/models/models -maxdepth 4 \( -iname '*hhem*' -o -iname '*ragtruth*' -o -iname '*kokoro*' -o -iname '*injection*' -o -iname '*simpleqa*' \) 2>/dev/null | head -40
h "V8 corpora"; ls -la /mnt/models/models/corpus /mnt/models/models/data 2>&1 | head -60
h "V9 27B timings last 24h"; journalctl -u llama-server --since "-24h" --no-pager | grep -E "prompt eval time|  eval time|draft acceptance" | tail -30
h "V10 reasoning switch in chat template"; curl -s -m 10 http://127.0.0.1:8080/props | python3 -c "import json,sys; print(json.load(sys.stdin).get('chat_template',''))" 2>&1 | grep -n -i -E "reasoning|enable_thinking" | head
h "V11 slots/metrics endpoints (HTTP codes)"; curl -s -m 10 -o /dev/null -w "slots %{http_code}\n" http://127.0.0.1:8080/slots; curl -s -m 10 -o /dev/null -w "metrics %{http_code}\n" http://127.0.0.1:8080/metrics
h "V12 update exposure"; apt-mark showhold; uname -r; dkms status 2>&1; grep -v '^\s*//' /etc/apt/apt.conf.d/50unattended-upgrades 2>&1 | grep -v '^\s*$' | head -40
h "V13 tailscale"; tailscale serve status 2>&1; tailscale status 2>&1 | head -20
h "V14 firewall"; sudo ufw status verbose 2>&1; sudo nft list ruleset 2>&1 | head -60
h "V15 backup tooling (names only)"; restic version 2>&1; ls -la ~/.config/jarvis/ 2>&1
h "V16 browser stack"; systemctl list-units --all --no-pager | grep -i -E "chrome|xvfb|vnc|browser"
h "V17 open-webui image"; sudo docker inspect open-webui --format '{{.Config.Image}} {{.Created}}' 2>&1
h "V18 USB tree"; lsusb -t
h "V19 NVMe PCIe link"; sudo lspci -vv 2>/dev/null | grep -A40 -i "non-volatile" | grep -E "LnkCap:|LnkSta:"
h "V20 glm-test load lines"; journalctl -u glm-test --no-pager 2>&1 | grep -i -E "load time|loaded|listening" | head
h "done"
