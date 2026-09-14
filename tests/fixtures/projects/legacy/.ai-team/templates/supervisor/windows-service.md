# Governed AI Team — Supervisor Daemon (Windows Task Scheduler / NSSM notes)
#
# Do NOT install system services during framework fabrication tests.
# Secrets must be supplied via the process environment or a protected env file —
# never on the command line.
#
# Option A — Task Scheduler (built-in, no pywin32):
#
#   schtasks /Create /TN "GovernedAISupervisor" /SC ONSTART /RL LIMITED ^
#     /TR "\"C:\Path\To\python.exe\" scripts\ai-team\daemon.py run --foreground --interval-seconds 5" ^
#     /WD "C:\Path\To\Project"
#
#   schtasks /Run /TN "GovernedAISupervisor"
#   schtasks /End /TN "GovernedAISupervisor"
#   schtasks /Delete /TN "GovernedAISupervisor" /F
#
# Option B — NSSM (optional external tool):
#
#   nssm install GovernedAISupervisor "C:\Path\To\python.exe"
#   nssm set GovernedAISupervisor AppDirectory "C:\Path\To\Project"
#   nssm set GovernedAISupervisor AppParameters "scripts\ai-team\daemon.py run --foreground --interval-seconds 5"
#   nssm set GovernedAISupervisor AppStdout "C:\Path\To\Project\.ai-team\supervisor\daemon.out.log"
#   nssm set GovernedAISupervisor AppStderr "C:\Path\To\Project\.ai-team\supervisor\daemon.err.log"
#   nssm set GovernedAISupervisor AppRestartDelay 5000
#   nssm start GovernedAISupervisor
#   nssm stop GovernedAISupervisor
#   nssm remove GovernedAISupervisor confirm
#
# Manual foreground (development / CI):
#
#   python scripts/ai-team/daemon.py run --foreground --interval-seconds 5
#
# Diagnostics:
#
#   python scripts/ai-team/daemon.py status --json
#   python scripts/ai-team/daemon.py doctor --json
