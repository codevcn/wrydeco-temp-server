import os
import paramiko
import sys

VPS_IP = '160.25.81.57'
VPS_USER = 'vmadmin'
VPS_PASSWORD = 'F8_OwEyj_Cod'
PROJECT_DIR = '/var/www/wrydeco-temp-server'
SERVICE_NAME = 'wrydeco-temp-server'

IGNORE_DIRS = {'.git', '__pycache__', '.venv', 'data', 'uploads', 'backup', '.playwright-mcp', 'node_modules'}

def sync_files(sftp, local_dir, remote_dir):
    for root, dirs, files in os.walk(local_dir):
        # Bỏ qua các thư mục không cần thiết
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        
        for file in files:
            # Bỏ qua file ẩn hoặc cấu hình không cần thiết nếu muốn, ở đây chỉ loại .gitignore cơ bản
            if file in {'.gitignore', '.DS_Store'}:
                continue
                
            local_path = os.path.join(root, file)
            rel_path = os.path.relpath(local_path, local_dir)
            # Dùng dấu / cho đường dẫn trên Linux
            remote_path = f"{remote_dir}/{rel_path.replace(os.sep, '/')}"
            
            # Đảm bảo thư mục đích tồn tại
            remote_dir_path = remote_path.rsplit('/', 1)[0]
            try:
                sftp.stat(remote_dir_path)
            except IOError:
                # Tạo thư mục theo từng cấp
                parts = remote_dir_path.replace(remote_dir, '').strip('/').split('/')
                current_dir = remote_dir
                for part in parts:
                    if part:
                        current_dir = f"{current_dir}/{part}"
                        try:
                            sftp.stat(current_dir)
                        except IOError:
                            sftp.mkdir(current_dir)
            
            # Upload file
            print(f"Uploading {rel_path} -> {remote_path}")
            sftp.put(local_path, remote_path)

def deploy():
    sys.stdout.reconfigure(encoding='utf-8')
    print("=== BƯỚC 1: KẾT NỐI VPS ===")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {VPS_USER}@{VPS_IP}...")
    try:
        client.connect(VPS_IP, username=VPS_USER, password=VPS_PASSWORD, timeout=10)
    except Exception as e:
        print(f"SSH error: {e}")
        sys.exit(1)

    print("\n=== BƯỚC 2: PHÂN QUYỀN THƯ MỤC TRÊN VPS ===")
    chown_cmd = f"echo '{VPS_PASSWORD}' | sudo -S chown -R {VPS_USER}:{VPS_USER} {PROJECT_DIR}"
    stdin, stdout, stderr = client.exec_command(chown_cmd)
    stdout.channel.recv_exit_status() # Chờ lệnh thực thi xong
    
    print("\n=== BƯỚC 3: SYNC FILES LÊN VPS ===")
    sftp = client.open_sftp()
    local_dir = os.path.abspath(os.path.dirname(__file__))
    sync_files(sftp, local_dir, PROJECT_DIR)
    sftp.close()

    print("\n=== BƯỚC 4: KHỞI ĐỘNG LẠI DỊCH VỤ TRÊN VPS ===")
    commands = [
        f"cd {PROJECT_DIR} && source .venv/bin/activate && pip install -r requirements.txt",
        f"echo '{VPS_PASSWORD}' | sudo -S systemctl restart {SERVICE_NAME}",
        f"systemctl status {SERVICE_NAME} --no-pager"
    ]

    for cmd in commands:
        print(f"\n[VPS] Running: {cmd}")
        stdin, stdout, stderr = client.exec_command(cmd)
        out = stdout.read().decode('utf-8', 'replace').encode('ascii', 'replace').decode('ascii')
        err = stderr.read().decode('utf-8', 'replace').encode('ascii', 'replace').decode('ascii')
        if out.strip(): print(out.strip())
        if err.strip(): print(err.strip())

    client.close()
    print("\n=== DEPLOY THÀNH CÔNG! ===")

if __name__ == '__main__':
    deploy()
