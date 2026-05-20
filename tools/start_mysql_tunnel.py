"""
Start SSH port-forward tunnel: localhost:13306 -> VPS:127.0.0.1:3306
Run once before starting Claude Code to enable MySQL MCP access.
Ctrl+C to stop.
"""
import socketserver
import threading
import paramiko
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

LOCAL_PORT = 13306
REMOTE_HOST = "127.0.0.1"
REMOTE_PORT = 3306


def _pump(src, dst):
    """Copy data from src to dst until EOF."""
    try:
        while True:
            data = src.recv(65535)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try:
            dst.close()
        except Exception:
            pass


def make_handler(transport, remote_host, remote_port):
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                chan = transport.open_channel(
                    "direct-tcpip",
                    (remote_host, remote_port),
                    self.request.getpeername(),
                )
            except Exception as e:
                print(f"Channel open failed: {e}")
                return

            # Two threads: one per direction
            t1 = threading.Thread(target=_pump, args=(self.request, chan), daemon=True)
            t2 = threading.Thread(target=_pump, args=(chan, self.request), daemon=True)
            t1.start()
            t2.start()
            t1.join()
            t2.join()
            chan.close()

    return Handler


class ForwardServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {VPS_HOST}...")
    client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=15)
    print(f"SSH connected. Forwarding localhost:{LOCAL_PORT} -> VPS:{REMOTE_PORT}")

    handler = make_handler(client.get_transport(), REMOTE_HOST, REMOTE_PORT)
    server = ForwardServer(("127.0.0.1", LOCAL_PORT), handler)
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
