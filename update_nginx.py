import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('160.25.81.57', username='vmadmin', password='F8_OwEyj_Cod', timeout=10)

commands = [
    "echo 'F8_OwEyj_Cod' | sudo -S sed -i 's/client_max_body_size 50M;/client_max_body_size 100M;/g' /etc/nginx/sites-available/vnote.io.vn",
    "echo 'F8_OwEyj_Cod' | sudo -S systemctl reload nginx"
]

for cmd in commands:
    stdin, stdout, stderr = client.exec_command(cmd)
    print(stdout.read().decode('utf-8'))
    print(stderr.read().decode('utf-8'))

client.close()
