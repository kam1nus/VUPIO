"""Windows desktop launcher; the UI opens in the installed default browser."""
import os
from pathlib import Path
import subprocess
import sys
import threading
import webbrowser

from mimic.models import tool
from mimic.server import ROOT, App, Handler, ThreadingHTTPServer, detect_lan
from mimic.windows_audio import WindowsAudio


def configure():
    base = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent
    tools = base / 'Tools'
    os.environ.setdefault('MIMIC_TOOLS', str(tools))
    os.environ.setdefault('MIMIC_BUNDLED_MODELS', str(base / 'Models'))
    os.environ['PATH'] = os.pathsep.join([str(tools/'ffmpeg'), os.environ.get('PATH','')])
    return Path(os.environ.get('MIMIC_DATA', Path(os.environ['LOCALAPPDATA'])/'MIMIC'))


def main():
    data = configure()
    if '--smoke-test' in sys.argv:
        import sounddevice
        for name, flag in [('ffmpeg','-version'),('ffprobe','-version'),
                           ('llama-server','--version'),('whisper-cli','--help')]:
            subprocess.run([tool(name),flag],check=True,stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
        return

    import tkinter as tk
    from tkinter import messagebox, ttk

    window = tk.Tk()
    window.title('VUPIO')
    window.iconphoto(True, tk.PhotoImage(file=str(ROOT/'web/vupio-icon-192.png')))
    window.resizable(False, False)
    window.withdraw()
    servers = []
    audio = app = None
    try:
        audio = WindowsAudio()
        host = detect_lan()
        port = int(os.environ.get('MIMIC_PORT', '8765'))
        local = ThreadingHTTPServer(('127.0.0.1',port), Handler)
        servers.append(local)
        if host != '127.0.0.1':
            try:
                servers.append(ThreadingHTTPServer((host, port), Handler))
            except OSError:
                host = '127.0.0.1'
        app = App(data,audio,host,port)
        for server in servers:
            server.daemon_threads = True
            server.app = app
            threading.Thread(target=server.serve_forever,daemon=True).start()
    except (ValueError, OSError) as error:
        for server in servers:
            server.server_close()
        if audio is not None:
            audio.close()
        messagebox.showerror('VUPIO', str(error), parent=window)
        window.destroy()
        return

    def open_board():
        webbrowser.open(f'http://127.0.0.1:{port}/#admin={app.admin_key}')

    panel = ttk.Frame(window, padding=22)
    panel.grid()
    ttk.Label(panel, text='VUPIO is running. Soundboard opens in your browser.').grid(sticky='w')
    ttk.Label(panel, text='Keep this window open while using VUPIO.').grid(sticky='w', pady=(4,14))
    ttk.Button(panel, text='Open Soundboard', command=open_board).grid(sticky='ew')
    if not audio.virtual_output:
        ttk.Button(panel, text='Official VB-CABLE driver',
                   command=lambda: webbrowser.open('https://vb-audio.com/Cable/')).grid(sticky='ew', pady=(8,0))
    ttk.Button(panel, text='Quit VUPIO', command=window.destroy).grid(sticky='ew', pady=(8,0))
    window.deiconify()
    window.after_idle(open_board)
    try:
        window.mainloop()
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        app.audio.close()
        if app._studio is not None:
            app._studio.close()


if __name__ == '__main__':
    main()
