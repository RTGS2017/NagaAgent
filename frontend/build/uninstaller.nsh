; OpenClaw 自动安装清理脚本
; 在卸载时检查是否是自动安装的 OpenClaw，如果是则清理相关文件

; 定义卸载版本的 StrContains 函数
Var UN_STR_HAYSTACK
Var UN_STR_NEEDLE
Var UN_STR_CONTAINS_VAR_1
Var UN_STR_CONTAINS_VAR_2
Var UN_STR_CONTAINS_VAR_3
Var UN_STR_CONTAINS_VAR_4
Var UN_STR_RETURN_VAR

Function un.StrContains
  Exch $UN_STR_NEEDLE
  Exch 1
  Exch $UN_STR_HAYSTACK
  StrCpy $UN_STR_RETURN_VAR ""
  StrCpy $UN_STR_CONTAINS_VAR_1 -1
  StrLen $UN_STR_CONTAINS_VAR_2 $UN_STR_NEEDLE
  StrLen $UN_STR_CONTAINS_VAR_4 $UN_STR_HAYSTACK
  un_loop:
    IntOp $UN_STR_CONTAINS_VAR_1 $UN_STR_CONTAINS_VAR_1 + 1
    StrCpy $UN_STR_CONTAINS_VAR_3 $UN_STR_HAYSTACK $UN_STR_CONTAINS_VAR_2 $UN_STR_CONTAINS_VAR_1
    StrCmp $UN_STR_CONTAINS_VAR_3 $UN_STR_NEEDLE un_found
    StrCmp $UN_STR_CONTAINS_VAR_1 $UN_STR_CONTAINS_VAR_4 un_done
    Goto un_loop
  un_found:
    StrCpy $UN_STR_RETURN_VAR $UN_STR_NEEDLE
    Goto un_done
  un_done:
   Pop $UN_STR_NEEDLE
   Exch $UN_STR_RETURN_VAR
FunctionEnd

!macro un.StrContains OUT NEEDLE HAYSTACK
  Push `${HAYSTACK}`
  Push `${NEEDLE}`
  Call un.StrContains
  Pop `${OUT}`
!macroend

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
  ${un.StrContains} $2 '"auto_installed": true' "$1"
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
