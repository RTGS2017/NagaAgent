; OpenClaw 自动安装清理脚本
; 在卸载时检查是否是自动安装的 OpenClaw，如果是则清理相关文件

!macro customUnInstall
  ; 检查 openclaw-runtime/.openclaw_install_state 文件
  IfFileExists "$INSTDIR\resources\openclaw-runtime\.openclaw_install_state" 0 SkipOpenClawCleanup

  ; 读取状态文件内容
  ClearErrors
  FileOpen $0 "$INSTDIR\resources\openclaw-runtime\.openclaw_install_state" r
  IfErrors SkipOpenClawCleanup

  ; 逐行读取文件，查找 auto_installed 标记
  StrCpy $2 "0"

ReadInstallStateLoop:
  ClearErrors
  FileRead $0 $1
  IfErrors ReadInstallStateDone

  ; 匹配 JSON 行前缀:   "auto_installed": true
  StrCpy $3 $1 24
  StrCmp $3 "  $\"auto_installed$\": true" 0 ReadInstallStateLoop
  StrCpy $2 "1"

  Goto ReadInstallStateDone

ReadInstallStateDone:
  FileClose $0

  ; 检查是否包含 "auto_installed": true
  StrCmp $2 "1" 0 SkipOpenClawCleanup

  ; 执行清理
  DetailPrint "检测到自动安装的 OpenClaw，正在清理..."

  ; 0. 先尝试停止内嵌 OpenClaw Gateway
  IfFileExists "$INSTDIR\resources\openclaw-runtime\openclaw\node_modules\.bin\openclaw.cmd" 0 SkipGatewayStop
  DetailPrint "正在停止内嵌 OpenClaw Gateway..."

  ; 最多重试 3 次
  StrCpy $5 "3"
StopGatewayRetry:
  ExecWait '"$SYSDIR\cmd.exe" /C ""$INSTDIR\resources\openclaw-runtime\openclaw\node_modules\.bin\openclaw.cmd" gateway stop"' $4
  StrCmp $4 "0" GatewayStopOk ContinueGatewayRetry

ContinueGatewayRetry:
  IntOp $5 $5 - 1
  IntCmp $5 0 GatewayStopFailed GatewayRetrySleep GatewayRetrySleep

GatewayRetrySleep:
  DetailPrint "停止 Gateway 失败（返回码: $4），剩余重试次数: $5"
  Sleep 1000
  Goto StopGatewayRetry

GatewayStopOk:
  DetailPrint "OpenClaw Gateway 已停止"
  Sleep 1000
  Goto SkipGatewayStop

GatewayStopFailed:
  DetailPrint "停止 Gateway 返回码: $4，继续清理"

  ; 1. 删除 openclaw 目录
SkipGatewayStop:
  RMDir /r "$INSTDIR\resources\openclaw-runtime\openclaw"

  ; 2. 删除用户配置目录 ~/.openclaw
  RMDir /r "$PROFILE\.openclaw"

  ; 3. 删除状态文件
  Delete "$INSTDIR\resources\openclaw-runtime\.openclaw_install_state"

  DetailPrint "OpenClaw 清理完成"

  SkipOpenClawCleanup:
!macroend
