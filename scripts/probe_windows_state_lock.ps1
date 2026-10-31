param([Parameter(Mandatory=$true)][string]$RunDirectory)
# Host-only diagnostic. Starts a WSL observer; no worker receives these privileges.
$ErrorActionPreference='Stop'
$resolved=[IO.Path]::GetFullPath($RunDirectory)
if(Test-Path -LiteralPath $resolved){throw 'Use a fresh run directory'}
New-Item -ItemType Directory -Path $resolved | Out-Null
$repo=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$linuxRepo=(& wsl -d Ubuntu-24.04 -- wslpath -u $repo.Replace('\','/')).Trim()
$linuxRun=(& wsl -d Ubuntu-24.04 -- wslpath -u $resolved.Replace('\','/')).Trim()
$target=Join-Path $resolved 'state.json'
[IO.File]::WriteAllText($target,'{"value":"before"}')
$reader=[IO.File]::Open($target,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
$process=$null
try {
  [IO.File]::WriteAllText((Join-Path $resolved 'locked'),'Windows reader holds state.json')
  $arguments=@('-d','Ubuntu-24.04','--cd',('"'+$linuxRepo+'"'),'--','/home/ws/.cache/researchsquad/verify-venv/bin/python','-m','scripts.probe_state_replace','--run-dir',('"'+$linuxRun+'"'))
  $process=Start-Process wsl.exe -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $resolved 'stdout.log') -RedirectStandardError (Join-Path $resolved 'stderr.log')
  $timer=[Diagnostics.Stopwatch]::StartNew()
  while(-not(Test-Path -LiteralPath (Join-Path $resolved 'attempted'))){
    if($process.HasExited -or $timer.Elapsed.TotalSeconds -gt 20){throw 'Observer did not reach replacement'}
    Start-Sleep -Milliseconds 10
  }
  Start-Sleep -Milliseconds 150
} finally {$reader.Dispose()}
if(-not $process.WaitForExit(20000)){throw 'Observer did not finish'}
if($process.ExitCode -ne 0){throw (Get-Content -Raw (Join-Path $resolved 'stderr.log'))}
Get-Content -Raw (Join-Path $resolved 'verification.json')
