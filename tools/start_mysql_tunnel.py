"""
Start SSH port-forward tunnel: localhost:13306 -> VPS:127.0.0.1:3306
Run once before starting Claude Code to enable MySQL MCP access.
Auto-reconnects on SSH transport failure. Ctrl+C to stop.
"""
import socketserver
import threading
import time
import paramiko
from deploy._vps_config import VPS_HOST, VPS_USER, VPS_PASSWORD

LOCAL_PORT = 13306
REMOTE_HOST = "127.0.0.1"
REMOTE_PORT = 3306
RECONNECT_DELAY = 5  # seconds between reconnect attempts


def _pump(src, dst):
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


def make_handler(transport_holder, remote_host, remote_port):
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            transport = transport_holder[0]
            if transport is None or not transport.is_active():
                print("SSH transport not active, dropping connection")
                return
            try:
                chan = transport.open_channel(
                    "direct-tcpip",
                    (remote_host, remote_port),
                    self.request.getpeername(),
                )
            except Exception as e:
                print(f"Channel open failed: {e}")
                return

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


def connect_ssh():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(VPS_HOST, username=VPS_USER, password=VPS_PASSWORD, timeout=15)
    client.get_transport().set_keepalive(30)
    return client


def monitor_transport(client_holder, transport_holder, stop_event):
    """Watch SSH transport; reconnect if it dies."""
    while not stop_event.is_set():
        time.sleep(10)
        transport = transport_holder[0]
        if transport is None or not transport.is_active():
            print("SSH transport lost, reconnecting...")
            try:
                old_client = client_holder[0]
                if old_client:
                    try:
                        old_client.close()
                    except Exception:
                        pass
                new_client = connect_ssh()
                client_holder[0] = new_client
                transport_holder[0] = new_client.get_transport()
                print(f"SSH reconnected. Tunnel active on localhost:{LOCAL_PORT}")
            except Exception as e:
                print(f"Reconnect failed: {e}, retrying in {RECONNECT_DELAY}s...")
                transport_holder[0] = None
                time.sleep(RECONNECT_DELAY)


def main():
    print(f"Connecting to {VPS_HOST}...")
    client = connect_ssh()
    print(f"SSH connected. Forwarding localhost:{LOCAL_PORT} -> VPS:{REMOTE_PORT}")

    transport_holder = [client.get_transport()]
    client_holder = [client]

    handler = make_handler(transport_holder, REMOTE_HOST, REMOTE_PORT)
    server = ForwardServer(("127.0.0.1", LOCAL_PORT), handler)
    print(f"Tunnel active on localhost:{LOCAL_PORT}. Press Ctrl+C to stop.")

    stop_event = threading.Event()
    monitor_thread = threading.Thread(
        target=monitor_transport,
        args=(client_holder, transport_holder, stop_event),
        daemon=True,
    )
    monitor_thread.start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nTunnel stopped.")
    finally:
        stop_event.set()
        server.server_close()
        if client_holder[0]:
            client_holder[0].close()


if __name__ == "__main__":
    main()
