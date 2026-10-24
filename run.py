from __future__ import annotations

import socket
import threading
import time
import webbrowser

import uvicorn

from app.main import app

HOST = "127.0.0.1"
PORT = 8000


def _wait_for_port(host: str, port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def main() -> None:
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level="info")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    def _open_browser() -> None:
        if _wait_for_port(HOST, PORT):
            try:
                webbrowser.open(f"http://{HOST}:{PORT}")
            except Exception:
                pass

    threading.Thread(target=_open_browser, daemon=True).start()

    try:
        input(
            "\n>>> Banking Legal Assistant đang chạy tại http://%s:%d\n>>> Nhấn Enter để dừng server và thoát...\n"
            % (HOST, PORT)
        )
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        server.should_exit = True
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
