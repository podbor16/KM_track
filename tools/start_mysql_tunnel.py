"""
Start SSH port-forward tunnel: localhost:13306 -> VPS:127.0.0.1:3306
Run once before starting Claude Code to enable MySQL MCP access.
Ctrl+C to stop.
"""
import select
import socketserver
import paramiko
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

LOCAL_PORT = 13306
REMOTE_HOST = "127.0.0.1"
REMOTE_PORT = 3306


def forward_tunnel(local_port, remote_host, remote_port, transport):
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                chan = transport.open_channel(
                    "direct-tcpip",
                    (remote_host, remote_port),
                    self.request.getpeername(),
                )
            except Exception as e:
                print(f"Forwarding failed: {e}")
                return
            while True:
                r, _, _ = select.select([self.request, chan], [], [])
                if self.request in r:
                    data = self.request.recv(1024)
                    if not data:
                        break
                    chan.send(data)
                if chan in r:
                    data = chan.recv(1024)
                    if not data:
                        break
                    self.request.send(data)
            chan.close()

    class ForwardServer(socketserver.ThreadingTCPServer):
        daemon_threads = True
        allow_reuse_address = True

    return ForwardServer(("127.0.0.1", local_port), Handler)


def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {VPS_HOST}...")
    client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=15)
    print(f"SSH connected. Forwarding localhost:{LOCAL_PORT} -> VPS:{REMOTE_PORT}")

    server = forward_tunnel(LOCAL_PORT, REMOTE_HOST, REMOTE_PORT, client.get_transport())
    print(f"Tunnel active on localhost:{LOCAL_PORT}. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nTunnel stopped.")
    finally:
        server.server_close()
        client.close()


if __name__ == "__main__":
    main()
