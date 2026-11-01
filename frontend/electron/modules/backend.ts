import type { Buffer } from 'node:buffer'
import type { ChildProcess } from 'node:child_process'
import { spawn, spawnSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'
import { app } from 'electron'
import { getMainWindow } from './window'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

let backendProcess: ChildProcess | null = null
let devRetryCount = 0
const BACKEND_LOG_MAX_LINES = 1200
const backendLogLines: string[] = []

function appendBackendLog(line: string, stream: 'stdout' | 'stderr' | 'system' = 'system') {
  const normalized = line.replace(/\r/g, '').trimEnd()
  if (!normalized.trim())
    return

  const entry = stream === 'system' ? normalized : `[${stream}] ${normalized}`
  backendLogLines.push(entry)
  if (backendLogLines.length > BACKEND_LOG_MAX_LINES) {
    backendLogLines.splice(0, backendLogLines.length - BACKEND_LOG_MAX_LINES)
  }

  try {
    getMainWindow()?.webContents.send('backend:log', { line: entry })
  }
  catch {
    // ignore renderer delivery failures
  }
}

function createChunkForwarder(
  stream: 'stdout' | 'stderr',
  onLine: (line: string) => boolean | void,
) {
  let carry = ''

  return (text: string) => {
    const normalized = `${carry}${text.replace(/\r\n/g, '\n').replace(/\r/g, '\n')}`
    const parts = normalized.split('\n')
    carry = parts.pop() ?? ''
    for (const part of parts) {
      const line = part.trimEnd()
      if (!line.trim())
        continue
      const shouldMirror = onLine(line)
      if (shouldMirror !== false) {
        appendBackendLog(line, stream)
      }
    }
  }
}

export function getBackendLogs(): string {
  return backendLogLines.join('\n')
}

interface AppPackageMetadata {
  nagaDebugConsole?: boolean
}

function shouldOpenDebugConsole(): boolean {
  // 方便本地联调：手动设置环境变量可强制开启
  if (process.env.NAGA_DEBUG_CONSOLE === '1') {
    return true
  }

  if (!app.isPackaged) {
    return false
  }

  try {
    const packageJsonPath = join(app.getAppPath(), 'package.json')
    const packageJson = JSON.parse(readFileSync(packageJsonPath, 'utf-8')) as AppPackageMetadata
    return packageJson.nagaDebugConsole === true
  }
  catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    console.warn(`[Backend] Failed to read debug build metadata: ${message}`)
    return false
  }
}

function quoteWindowsArg(arg: string): string {
  if (arg.length === 0) {
    return '""'
  }
  if (!/[\s"]/u.test(arg)) {
    return arg
  }
  return `"${arg.replaceAll('"', '""')}"`
}

function resolveVenvPython(cwd: string): string {
  return process.platform === 'win32'
    ? join(cwd, '.venv', 'Scripts', 'python.exe')
    : join(cwd, '.venv', 'bin', 'python')
}

function resolveVenvUv(cwd: string): string | null {
  const candidate = process.platform === 'win32'
    ? join(cwd, '.venv', 'Scripts', 'uv.exe')
    : join(cwd, '.venv', 'bin', 'uv')
  return existsSync(candidate) ? candidate : null
}

export function startBackend(): void {
  let cmd: string
  let args: string[]
  let cwd: string

  if (app.isPackaged) {
    // 打包模式：spawn PyInstaller 编译的二进制
    const backendDir = join(process.resourcesPath, 'backend')
    const ext = process.platform === 'win32' ? '.exe' : ''
    cmd = join(backendDir, `naga-backend${ext}`)
    args = []
    cwd = backendDir
  }
  else {
    // 开发模式：优先使用 venv 中的 Python 解释器，确保依赖版本一致
    cwd = join(__dirname, '..', '..')
    cmd = resolveVenvPython(cwd)
    args = ['main.py', '--headless']
  }

  console.log(`[Backend] Starting from ${cwd}`)
  console.log(`[Backend] Command: ${cmd} ${args.join(' ')}`)
  appendBackendLog(`[Backend] Starting from ${cwd}`)
  appendBackendLog(`[Backend] Command: ${cmd} ${args.join(' ')}`)

  const env: Record<string, string | undefined> = {
    ...process.env,
    PYTHONUNBUFFERED: '1',
    PYTHONIOENCODING: 'utf-8',
    PYTHONUTF8: '1',
  }

  const useDebugConsole = process.platform === 'win32' && shouldOpenDebugConsole()

  if (useDebugConsole) {
    const commandLine = [cmd, ...args].map(quoteWindowsArg).join(' ')
    console.log('[Backend] Debug console enabled, launching with cmd.exe /k')
    appendBackendLog('[Backend] Debug console enabled, backend logs are not mirrored while cmd.exe /k is active.')

    backendProcess = spawn('cmd.exe', ['/d', '/k', commandLine], {
      cwd,
      env,
      stdio: 'inherit',
      windowsHide: false,
    })

    backendProcess.on('error', (err) => {
      console.error(`[Backend] Failed to start (debug console): ${err.message}`)
      appendBackendLog(`[Backend] Failed to start (debug console): ${err.message}`)
    })

    backendProcess.on('exit', (code) => {
      console.log(`[Backend] Debug console exited with code ${code}`)
      appendBackendLog(`[Backend] Debug console exited with code ${code}`)
      backendProcess = null
    })
    return
  }

  // Dev mode: collect stderr for dependency error detection
  let stderrBuffer = ''
  // Collect all output for error reporting
  const outputLines: string[] = []
  const PROGRESS_PREFIX = '##PROGRESS##'
  const consumeStdoutChunk = createChunkForwarder('stdout', (trimmed) => {
    outputLines.push(trimmed)

    if (trimmed.startsWith(PROGRESS_PREFIX)) {
      try {
        const payload = JSON.parse(trimmed.slice(PROGRESS_PREFIX.length))
        getMainWindow()?.webContents.send('backend:progress', payload)
      }
      catch {
        // malformed progress line, ignore
      }
      return false
    }
    return true
  })
  const consumeStderrChunk = createChunkForwarder('stderr', (trimmed) => {
    outputLines.push(trimmed)
    if (!app.isPackaged) {
      stderrBuffer += `${trimmed}\n`
    }
    return true
  })

  backendProcess = spawn(cmd, args, {
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    env,
    // 创建独立进程组，关闭时用 process.kill(-pid) 杀掉所有子进程
    detached: process.platform !== 'win32',
  })

  backendProcess.stdout?.setEncoding('utf-8')
  backendProcess.stderr?.setEncoding('utf-8')

  backendProcess.stdout?.on('data', (text: string) => {
    consumeStdoutChunk(text)
    console.log(`[Backend] ${text.trimEnd()}`)
  })

  backendProcess.stderr?.on('data', (text: string) => {
    console.error(`[Backend] ${text.trimEnd()}`)
    consumeStderrChunk(text)
  })

  backendProcess.on('error', (err) => {
    console.error(`[Backend] Failed to start: ${err.message}`)
    appendBackendLog(`[Backend] Failed to start: ${err.message}`)
  })

  backendProcess.on('exit', (code) => {
    console.log(`[Backend] Exited with code ${code}`)
    appendBackendLog(`[Backend] Exited with code ${code}`)
    backendProcess = null

    // Notify renderer of backend crash (non-zero exit, not a manual stop)
    if (code !== null && code !== 0) {
      const logs = outputLines.slice(-200).join('\n')
      getMainWindow()?.webContents.send('backend:error', { code, logs })
    }

    // Dev-only auto-recovery: detect dependency errors and retry once
    if (!app.isPackaged && code === 1 && devRetryCount < 1) {
      const depErrorPattern = /ModuleNotFoundError|ImportError|No module named/u
      if (depErrorPattern.test(stderrBuffer)) {
        devRetryCount++
        console.log('[Backend] Dependency error detected, auto-installing...')
        appendBackendLog('[Backend] Dependency error detected, auto-installing...')

        const venvPython = resolveVenvPython(cwd)
        const reqFile = join(cwd, 'requirements.txt')
        const venvUv = resolveVenvUv(cwd)

        // Prefer the project venv's uv; if it is absent, try python -m uv before falling back to pip.
        let installOk = false
        if (venvUv) {
          const uvResult = spawnSync(venvUv, ['pip', 'install', '--python', venvPython, '-r', reqFile], {
            cwd,
            stdio: 'inherit',
            timeout: 120_000,
          })
          installOk = uvResult.status === 0
        }
        if (!installOk) {
          const uvModuleResult = spawnSync(venvPython, ['-m', 'uv', 'pip', 'install', '-r', reqFile], {
            cwd,
            stdio: 'inherit',
            timeout: 120_000,
          })
          installOk = uvModuleResult.status === 0
        }
        if (!installOk) {
          console.log('[Backend] Internal uv unavailable, falling back to pip...')
          const pipResult = spawnSync(venvPython, ['-m', 'pip', 'install', '-r', reqFile], {
            cwd,
            stdio: 'inherit',
            timeout: 120_000,
          })
          installOk = pipResult.status === 0
        }

        if (installOk) {
          console.log('[Backend] Dependencies installed, restarting backend...')
          appendBackendLog('[Backend] Dependencies installed, restarting backend...')
          startBackend()
        }
        else {
          console.error('[Backend] Dependency installation failed. Please install manually.')
          appendBackendLog('[Backend] Dependency installation failed. Please install manually.')
        }
      }
    }
  })
}

export function stopBackend(): void {
  if (!backendProcess)
    return
  const pid = backendProcess.pid
  console.log('[Backend] Stopping...')
  appendBackendLog('[Backend] Stopping...')

  if (!pid) {
    backendProcess = null
    return
  }

  if (process.platform === 'win32') {
    // /T 连同子进程树一起终止
    spawn('taskkill', ['/pid', String(pid), '/f', '/t'])
  }
  else {
    // 杀整个进程组（负 PID），确保 uvicorn workers 等子进程一起退出
    try {
      process.kill(-pid, 'SIGTERM')
    }
    catch {
      // 进程组不存在，回退杀单个进程
      try {
        process.kill(pid, 'SIGTERM')
      }
      catch {
        /* already dead */
      }
    }
    // 保险：200ms 后 SIGKILL 整个进程组
    setTimeout(() => {
      try {
        process.kill(-pid, 'SIGKILL')
      }
      catch {
        try {
          process.kill(pid, 'SIGKILL')
        }
        catch {
          /* already dead */
        }
      }
    }, 200)
  }

  backendProcess = null
}
