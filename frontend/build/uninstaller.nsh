; OpenClaw 自动安装清理脚本
; 在卸载时检查是否是自动安装的 OpenClaw，如果是则清理相关文件

!include "StrContains.nsh"

!macro customUnInstall
  ; 检查 openclaw-runtime/.openclaw_install_state 文件
  IfFileExists "$INSTDIR\resources\openclaw-runtime\.openclaw_install_state" 0 SkipOpenClawCleanup

  ; 读取状态文件内容
  ClearErrors
  FileOpen $0 "$INSTDIR\resources\openclaw-runtime\.openclaw_install_state" r
  IfErrors SkipOpenClawCleanup

  ; 读取文件内容到 $1
  FileRead $0 $1
  FileClose $0

  ; 检查是否包含 "auto_installed": true
  ${StrContains} $2 '"auto_installed": true' "$1"
  StrCmp $2 "" SkipOpenClawCleanup 0

  ; 执行清理
  DetailPrint "检测到自动安装的 OpenClaw，正在清理..."

  ; 1. 删除 openclaw 目录
  RMDir /r "$INSTDIR\resources\openclaw-runtime\openclaw"

  ; 2. 删除用户配置目录 ~/.openclaw
  RMDir /r "$PROFILE\.openclaw"

  ; 3. 删除状态文件
  Delete "$INSTDIR\resources\openclaw-runtime\.openclaw_install_state"

  DetailPrint "OpenClaw 清理完成"

  SkipOpenClawCleanup:
!macroend
