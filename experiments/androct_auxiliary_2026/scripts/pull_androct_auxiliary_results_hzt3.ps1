$ErrorActionPreference = 'Stop'

$PackageDir = 'G:\CIKM2026_network_agent_safety_package_20260515_134609'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$Dest = Join-Path $PackageDir ("07_androct_auxiliary_results_hzt3_" + $Stamp)
$RemoteDir = Join-Path $Dest 'remote_archive'
$LocalCtx = Join-Path $Dest 'local_context'
New-Item -ItemType Directory -Force -Path $RemoteDir, $LocalCtx | Out-Null

$Key = if ($env:MATPOOL_SSH_KEY) { $env:MATPOOL_SSH_KEY } else { '<SSH_KEY_PATH>' }
if ($Key -eq '<SSH_KEY_PATH>') {
  throw 'Set MATPOOL_SSH_KEY to the private SSH key path before running this script.'
}
$HostSpec = if ($env:MATPOOL_HOST_SPEC) { $env:MATPOOL_HOST_SPEC } else { '<USER>@<HOST>' }
$Port = if ($env:MATPOOL_PORT) { $env:MATPOOL_PORT } else { '<PORT>' }
if ($HostSpec -eq '<USER>@<HOST>' -or $Port -eq '<PORT>') {
  throw 'Set MATPOOL_HOST_SPEC and MATPOOL_PORT before running this script.'
}

$StatusCmd = @'
BASE=/root/experiments/androct_auxiliary
echo "# AndroCT auxiliary final status"
echo
echo "- time_utc: $(date -Is)"
echo "- summaries: $(find "$BASE/outputs" -type f -name "*_summary.csv" 2>/dev/null | wc -l)"
echo "- running_aux_tmux: $(tmux ls 2>/dev/null | grep -c "^androct_aux_y" || true)"
echo "- nonzero_exit_files: $(find "$BASE/logs" -type f -name "androct_aux_y*.exit" -exec sh -c '\''for f; do [ "$(cat "$f" 2>/dev/null)" != "0" ] && echo "$f"; done'\'' sh {} + 2>/dev/null | wc -l)"
echo
cat "$BASE/state/queue_status.env" 2>/dev/null || true
echo
tail -80 "$BASE/logs/auxiliary_queue_daemon.log" 2>/dev/null || true
'@
& ssh -i $Key -p $Port $HostSpec $StatusCmd | Tee-Object -FilePath (Join-Path $Dest 'REMOTE_AUXILIARY_STATUS.md') | Out-Null

$ArchiveCmd = @'
set -e
BASE=/root/experiments/androct_auxiliary
STAMP=$(date +%Y%m%d_%H%M%S)
ARCH=/tmp/androct_auxiliary_${STAMP}.tgz
cd "$BASE"
tar -czf "$ARCH" outputs logs scripts state EXPERIMENT_PROCESS.md
echo "$ARCH"
echo "summary_count=$(find outputs -type f -name "*_summary.csv" 2>/dev/null | wc -l)"
echo "archive_size=$(du -h "$ARCH" | cut -f1)"
'@
$RemoteOut = & ssh -i $Key -p $Port $HostSpec $ArchiveCmd
$RemoteOut | Out-File -Encoding UTF8 -FilePath (Join-Path $Dest 'REMOTE_AUXILIARY_ARCHIVE_COMMAND_OUTPUT.txt')
$RemoteArchive = $RemoteOut | Where-Object { $_ -like '/tmp/*.tgz' } | Select-Object -Last 1
if (-not $RemoteArchive) { throw 'Remote auxiliary archive path not found.' }

$LocalArchive = Join-Path $Dest 'remote_auxiliary_outputs_logs_scripts.tgz'
& scp -i $Key -P $Port ($HostSpec + ':' + $RemoteArchive) $LocalArchive
& tar -xzf $LocalArchive -C $RemoteDir

Get-ChildItem -LiteralPath $RemoteDir -Recurse -File |
  Select-Object FullName,Length,LastWriteTime |
  Export-Csv -NoTypeInformation -Encoding UTF8 (Join-Path $Dest 'AUXILIARY_PULLED_FILES_INDEX.csv')

Get-ChildItem -LiteralPath $RemoteDir -Recurse -File -Include *.csv,*.md |
  Select-Object FullName,Length,LastWriteTime |
  Export-Csv -NoTypeInformation -Encoding UTF8 (Join-Path $Dest 'AUXILIARY_PULLED_CSV_MD_INDEX.csv')

$SummaryFiles = Get-ChildItem -LiteralPath $RemoteDir -Recurse -File -Filter '*_summary.csv'
$Rows = @()
foreach($f in $SummaryFiles){
  $rel = $f.FullName.Substring($RemoteDir.Length + 1)
  $task = Split-Path (Split-Path $rel -Parent) -Leaf
  $Rows += Import-Csv -LiteralPath $f.FullName | ForEach-Object {
    $_ | Add-Member -NotePropertyName source_file -NotePropertyValue $rel -Force
    $_ | Add-Member -NotePropertyName task_name -NotePropertyValue $task -Force
    $_
  }
}
$Rows | Export-Csv -NoTypeInformation -Encoding UTF8 (Join-Path $Dest 'ANDROCT_AUXILIARY_MERGED_SUMMARIES.csv')

$ScriptSrc = 'F:\work\submissions\network_agent_safety\scripts'
$ScriptDest = Join-Path $LocalCtx 'scripts'
New-Item -ItemType Directory -Force -Path $ScriptDest | Out-Null
Get-ChildItem -LiteralPath $ScriptSrc -File -Include '*androct_auxiliary*','launch_androct_auxiliary_hzt3.sh','monitor_androct_auxiliary_hzt3.sh','pull_androct_auxiliary_results_hzt3.ps1' |
  Copy-Item -Destination $ScriptDest -Force

@"
# AndroCT auxiliary sync summary

Created: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')

- Pulled summary CSV files: $($SummaryFiles.Count)
- Merged summary rows: $($Rows.Count)
- Remote archive: `$RemoteArchive`
- Local archive: `remote_auxiliary_outputs_logs_scripts.tgz`

Raw AndroCT data archives are not copied.
"@ | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $Dest 'ANDROCT_AUXILIARY_SYNC_SUMMARY.md')

Write-Output "dest=$Dest"
Write-Output "summary_files=$($SummaryFiles.Count)"
Write-Output "merged_rows=$($Rows.Count)"
