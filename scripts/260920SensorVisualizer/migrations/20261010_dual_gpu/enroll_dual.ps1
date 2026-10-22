$taskConfig = Join-Path $PSScriptRoot 'targets.json'
& 'D:/Anaconda3/python.exe' -X utf8 'C:/Users/15452/.codex/skills/cloud-instance-ops/scripts/ops.py' --config $taskConfig credential-set --target isaac-dual --task dual-gpu-credential-enrollment --purpose '在隐藏输入中登记双卡实例凭据，不改变远端密码'
if ($LASTEXITCODE -ne 0) { throw 'Credential enrollment did not complete' }
