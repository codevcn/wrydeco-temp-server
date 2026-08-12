import os
import subprocess
import paramiko
import sys

VPS_IP = '160.25.81.57'
VPS_USER = 'vmadmin'
VPS_PASSWORD = 'F8_OwEyj_Cod'
PROJECT_DIR = '/var/www/wrydeco-temp-server'
SERVICE_NAME = 'wrydeco-temp-server'

def run_local(command):
    print(f"[LOCAL] Running: {command}")
    result = subprocess.run(command, shell=True, text=True, capture_output=True)
    if result.returncode != 0:
        print(f"[LOCAL] Error:\n{result.stderr}")
        sys.exit(1)
    print(result.stdout)

def deploy():
    print("=== BƯỚC 1: COMMIT & PUSH (LOCAL) ===")
    run_local("git add .")
    status = subprocess.run("git status --porcelain", shell=True, capture_output=True, text=True)
    if status.stdout.strip():
        run_local("git commit -m \"Auto deploy from Antigravity Agent: add Export Data ZIP feature\"")
        run_local("git push origin main")
    else:
        print("Khong co thay doi de commit. Tiep tuc deploy.")
    
    print("\n=== BƯỚC 2: DEPLOY TRÊN VPS ===")
    sys.stdout.reconfigure(encoding='utf-8')
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {VPS_USER}@{VPS_IP}...")
    try:
        client.connect(VPS_IP, username=VPS_USER, password=VPS_PASSWORD, timeout=10)
    except Exception as e:
        print(f"SSH error: {e}")
        sys.exit(1)

    # Chạy các lệnh an toàn bằng sudo -S để truyền mật khẩu
    commands = [
        f"echo '{VPS_PASSWORD}' | sudo -S chown -R {VPS_USER}:{VPS_USER} {PROJECT_DIR}",
        f"cd {PROJECT_DIR} && git pull origin main",
        f"cd {PROJECT_DIR} && source .venv/bin/activate && pip install -r requirements.txt",
        f"echo '{VPS_PASSWORD}' | sudo -S systemctl restart {SERVICE_NAME}",
        f"systemctl status {SERVICE_NAME} --no-pager"
    ]

    for cmd in commands:
        print(f"\n[VPS] Running: {cmd}")
        stdin, stdout, stderr = client.exec_command(cmd)
        # Read outputs
        out = stdout.read().decode('utf-8', 'replace').encode('ascii', 'replace').decode('ascii')
        err = stderr.read().decode('utf-8', 'replace').encode('ascii', 'replace').decode('ascii')
        if out.strip(): print(out.strip())
        if err.strip(): print(err.strip())

    client.close()
    print("\n=== DEPLOY THÀNH CÔNG! ===")

if __name__ == '__main__':
    deploy()
