import type { Buffer } from 'node:buffer'
import type { ChildProcess } from 'node:child_process'
import { spawn } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'
import { app } from 'electron'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

let backendProcess: ChildProcess | null = null

type AppPackageMetadata = {
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
    // 开发模式：直接用 python
    cwd = join(__dirname, '..', '..')
    cmd = process.platform === 'win32' ? 'python' : 'python3'
    args = ['main.py']
  }

  console.log(`[Backend] Starting from ${cwd}`)
  console.log(`[Backend] Command: ${cmd} ${args.join(' ')}`)

  const env = { ...process.env, PYTHONUNBUFFERED: '1' }
  const useDebugConsole = process.platform === 'win32' && shouldOpenDebugConsole()

  if (useDebugConsole) {
    const commandLine = [cmd, ...args].map(quoteWindowsArg).join(' ')
    console.log('[Backend] Debug console enabled, launching with cmd.exe /k')

    backendProcess = spawn('cmd.exe', ['/d', '/k', commandLine], {
      cwd,
      env,
      stdio: 'inherit',
      windowsHide: false,
    })

    backendProcess.on('error', (err) => {
      console.error(`[Backend] Failed to start (debug console): ${err.message}`)
    })

    backendProcess.on('exit', (code) => {
      console.log(`[Backend] Debug console exited with code ${code}`)
      backendProcess = null
    })
    return
  }

  backendProcess = spawn(cmd, args, {
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    env,
  })

  backendProcess.stdout?.on('data', (data: Buffer) => {
    console.log(`[Backend] ${data.toString().trimEnd()}`)
  })

  backendProcess.stderr?.on('data', (data: Buffer) => {
    console.error(`[Backend] ${data.toString().trimEnd()}`)
  })

  backendProcess.on('error', (err) => {
    console.error(`[Backend] Failed to start: ${err.message}`)
  })

  backendProcess.on('exit', (code) => {
    console.log(`[Backend] Exited with code ${code}`)
    backendProcess = null
  })
}

export function stopBackend(): void {
  if (!backendProcess)
    return
  const pid = backendProcess.pid
  console.log('[Backend] Stopping...')

  if (!pid) {
    backendProcess = null
    return
  }

  if (process.platform === 'win32') {
    spawn('taskkill', ['/pid', String(pid), '/f', '/t'])
  } else {
    // Send SIGTERM first, then SIGKILL immediately after
    try {
      if (pid) process.kill(pid, 'SIGTERM')
    } catch {
      // already dead
    }
    // Force kill after 1s — must be short since Electron is exiting
    try {
      if (pid) {
        const timer = setTimeout(() => {
          try {
            process.kill(pid, 'SIGKILL')
          } catch {
            // already dead
          }
        }, 1000)
        timer.unref() // Don't block Electron exit
      }
    } catch {
      // already dead
    }
  }

  backendProcess = null
}
