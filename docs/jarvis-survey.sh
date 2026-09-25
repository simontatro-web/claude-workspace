#!/bin/bash
# Read-only state survey for jarvis-1. Changes nothing. Prints no keys or secrets.
{
echo "== date"; date -u
echo "== services"; systemctl list-units --type=service --all --no-pager --plain 'jarvis*' 'llama*' 'gpu-tune*' 'nvidia*' 2>&1 | head -30
echo "== unit files"; ls /etc/systemd/system | grep -E 'jarvis|llama|gpu|nvidia'
echo "== llama-server ExecStart"; systemctl cat llama-server.service 2>/dev/null | grep -E '^ExecStart|^Environment'
echo "== tool server ExecStart"; systemctl cat jarvis-run-host-commands.service 2>/dev/null | grep -E '^ExecStart'
echo "== listening ports"; ss -ltn | awk 'NR>1{print $4}' | sort -u
echo "== GPUs"; nvidia-smi --query-gpu=index,driver_version,memory.used,memory.total,ecc.mode.current,power.limit,temperature.gpu --format=csv
echo "== held packages"; apt-mark showhold
echo "== tuning"; echo -n "numa_balancing="; cat /proc/sys/kernel/numa_balancing; echo -n "governor="; cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor; systemctl is-active jarvis-perf.service
echo "== memory and disk"; free -g | head -2; df -h / | tail -1; lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT | grep -v loop
echo "== groups"; id
echo "== home"; ls ~
echo "== jarvis-memory"; ls -la ~/jarvis-memory ~/jarvis-memory/findings 2>&1 | head -40
echo "== plugins"; ls ~/jarvis-tools/plugins 2>&1
echo "== llama.cpp arch support"; for a in qwen4exp glm-dsa glm5next hy_v4 mimo2 deepseek4; do echo -n "$a: "; grep -rl "\"$a\"" ~/llama.cpp/src/llama-arch.cpp >/dev/null 2>&1 && echo yes || echo no; done
echo "== tailscale serve"; tailscale serve status 2>&1 | head -20
echo "== open webui"; curl -s -o /dev/null -w "port 3000 -> %{http_code}\n" http://127.0.0.1:3000/
sudo docker exec -i open-webui python3 - <<'PY'
import sqlite3, json
c = sqlite3.connect('/app/backend/data/webui.db')
for mid, params, meta in c.execute("select id, params, meta from model"):
    p = json.loads(params or '{}'); m = json.loads(meta or '{}')
    s = p.get('system') or ''
    print(mid, '| system prompt chars:', len(s),
          '| sections present:', [h for h in ('## 13', '## 14', '## 19') if h in s],
          '| temperature:', p.get('temperature'), '| num_ctx:', p.get('num_ctx'),
          '| function_calling:', p.get('function_calling'),
          '| builtin_tools:', (m.get('capabilities') or {}).get('builtin_tools'))
PY
echo "== truncation events since boot"; journalctl -u llama-server -b --no-pager 2>/dev/null | grep -c "truncated = 1"
echo "== NVMe health"; sudo nvme smart-log /dev/nvme0 2>/dev/null | grep -E 'critical_warning|available_spare|percentage_used|media_errors'
} 2>&1 | tee ~/jarvis-survey.txt
