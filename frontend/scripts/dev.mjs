import { execSync, spawn } from 'node:child_process'
import process from 'node:process'

if (process.platform === 'win32') {
  try {
    execSync('chcp 65001', { stdio: 'ignore' })
  }
  catch {}
}

const child = spawn('npx', ['vite'], {
  stdio: 'inherit',
  shell: true,
})

child.on('exit', code => process.exit(code ?? 0))
