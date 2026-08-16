# 安装机核播客日历的 Windows 计划任务（用 Register-ScheduledTask，无需管理员）
# 用法：powershell -ExecutionPolicy Bypass -File install_task.ps1
$ErrorActionPreference = "Stop"

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$gcal = Join-Path $dir "gcal.py"

# 解析真实 Python 解释器路径（计划任务环境无 PATH，必须用绝对路径）
$pyReal = & py -c "import sys; print(sys.executable)" 2>$null
if (-not $pyReal) {
    Write-Warning "未找到 py 启动器，请先安装 Python 3.11+"
    exit 1
}
$pyw = Join-Path (Split-Path $pyReal) "pythonw.exe"
if (Test-Path $pyw) { $pyExe = $pyw } else { $pyExe = $pyReal }
Write-Host "Python 解释器: $pyExe"

Write-Host "安装机核播客日历定时任务..."
Write-Host "脚本目录: $dir"

function New-GcalTask {
    param(
        [string]$Name,
        [string]$Argument,
        [scriptblock]$TriggerFactory
    )
    $action = New-ScheduledTaskAction -Execute $pyExe -Argument $Argument -WorkingDirectory $dir
    $trigger = & $TriggerFactory
    try {
        Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger `
            -Description "机核播客日历 $Name" -Force | Out-Null
        Write-Host "已创建任务: $Name"
    } catch {
        Write-Warning "创建任务 $Name 失败: $($_.Exception.Message)"
    }
}

# 1) 每日 12:00（中午）一条龙：备份 + 增量抓取 + 播放快照 + 完整性自检
New-GcalTask -Name "GcoresCalendarDaily" `
    -Argument ('"' + $gcal + '" daily') `
    -TriggerFactory { New-ScheduledTaskTrigger -Daily -At 12:00 }

# 2) 每 6 小时轻量增量
New-GcalTask -Name "GcoresCalendarHourly" `
    -Argument ('"' + $gcal + '" incremental') `
    -TriggerFactory { New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) `
        -RepetitionInterval (New-TimeSpan -Hours 6) }

Write-Host ""
Write-Host "说明："
Write-Host "  1. 首次使用请先手动执行全量回填：py $gcal init / backfill / comments"
Write-Host "  2. 查看任务：Get-ScheduledTask -TaskName GcoresCalendar*"
Write-Host "  3. 卸载任务：Unregister-ScheduledTask -TaskName GcoresCalendarDaily -Confirm:`$false"
Write-Host "  4. 任务日志：$dir\logs\gcal.log"
