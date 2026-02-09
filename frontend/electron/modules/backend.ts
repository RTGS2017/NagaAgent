import { spawn } from 'child_process'
import type { ChildProcess } from 'child_process'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
import { app } from 'electron'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

let backendProcess: ChildProcess | null = null

export function startBackend(): void {
  let cmd: string
  let args: string[]
  let cwd: string

  if (app.isPackaged) {
    // 打包模式：spawn PyInstaller 编译的二进制
    const backendDir = join(process.resourcesPath, 'backend')
    const ext = process.platform === 'win32' ? '.exe' : ''
    cmd = join(backendDir, `naga-backend${ext}`)
    args = ['--headless']
    cwd = backendDir
  } else {
    // 开发模式：直接用 python
    cwd = join(__dirname, '..', '..')
    cmd = process.platform === 'win32' ? 'python' : 'python3'
    args = ['main.py', '--headless']
  }

  console.log(`[Backend] Starting from ${cwd}`)
  console.log(`[Backend] Command: ${cmd} ${args.join(' ')}`)

  backendProcess = spawn(cmd, args, {
    cwd,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
    detached: true,
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
  if (!backendProcess) return
  const pid = backendProcess.pid
  console.log('[Backend] Stopping...')

  if (process.platform === 'win32') {
    // On Windows, use taskkill to kill the process tree
    spawn('taskkill', ['/pid', String(pid), '/f', '/t'])
  } else {
    // Kill the entire process group (negative PID)
    try {
      if (pid) process.kill(-pid, 'SIGTERM')
    } catch {
      // already dead
    }
    // Force kill after 5s if still alive
    setTimeout(() => {
      try {
        if (pid) process.kill(-pid, 0) // check if alive
        process.kill(-pid!, 'SIGKILL')
      } catch {
        // already dead
      }
    }, 5000)
  }

  backendProcess = null
}
