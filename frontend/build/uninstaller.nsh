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

  ; 1. 删除 openclaw 目录
  RMDir /r "$INSTDIR\resources\openclaw-runtime\openclaw"

  ; 2. 删除用户配置目录 ~/.openclaw
  RMDir /r "$PROFILE\.openclaw"

  ; 3. 删除状态文件
  Delete "$INSTDIR\resources\openclaw-runtime\.openclaw_install_state"

  DetailPrint "OpenClaw 清理完成"

  SkipOpenClawCleanup:
!macroend
