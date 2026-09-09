"""Desktop launcher; worker modes also support the packaged Windows executable."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import zipfile

APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))


def worker_command(mode, args):
    if getattr(sys, 'frozen', False):
        return [sys.executable, mode, *args]
    return [sys.executable, str(Path(__file__).resolve()), mode, *args]


def install_world(ap_path):
    """Install without overwriting an existing world."""
    ap = Path(ap_path).resolve()
    if not ((ap / 'ArchipelagoGenerate.exe').is_file() or (ap / 'Generate.py').is_file()):
        raise ValueError('Select the folder containing ArchipelagoGenerate.exe or Generate.py.')
    if (ap / 'worlds' / 'roster').exists():
        return 'Roster is already installed as source. Update that copy with git pull.'
    target = ap / 'custom_worlds' / 'roster.apworld'
    target.parent.mkdir(exist_ok=True)
    if target.exists():
        return 'Roster is installed. Move the old roster.apworld out of custom_worlds before replacing it.'
    source = RESOURCE_DIR / 'worlds' / 'roster'
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob('*')):
            relative = path.relative_to(source)
            if not path.is_file() or '__pycache__' in relative.parts or 'test' in relative.parts:
                continue
            if path.suffix not in ('.py', '.json', '.md'):
                continue
            if str(relative) == 'archipelago.json':
                manifest = json.loads(path.read_text(encoding='utf-8'))
                manifest.update(compatible_version=7, version=7)
                archive.writestr('roster/archipelago.json', json.dumps(manifest))
            else:
                archive.write(path, 'roster/' + relative.as_posix())
    return 'Roster installed. Each candidate game also needs its apworld installed in Archipelago.'


class Launcher:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk
        self.root, self.events = root, queue.Queue()
        self.busy = False
        self.result = None
        root.title('Roster')
        root.geometry('800x790')
        root.minsize(720, 730)
        root.protocol('WM_DELETE_WINDOW', self.close)
        ttk.Style(root).configure('Title.TLabel', font=('Segoe UI', 22, 'bold'))
        frame = ttk.Frame(root, padding=24)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Roster', style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame, text='Pick a surprise lineup. Reveal each game when it unlocks.').pack(anchor='w', pady=(0, 16))
        defaults = [Path('D:/Archipelago'), Path('C:/ProgramData/Archipelago'), Path.home() / 'Archipelago']
        self.ap = tk.StringVar(value=next((str(p) for p in defaults if p.exists()), ''))
        self.games = tk.StringVar(value=str(APP_DIR / 'games'))
        self.output = tk.StringVar(value=str(APP_DIR / 'output'))
        self.pick, self.start, self.seed = tk.StringVar(value='10'), tk.StringVar(value='2'), tk.StringVar()
        self.server = tk.StringVar()
        self.tracker_slot = tk.StringVar(value='Game 01')
        self.inputs = []
        for label, variable in [('Archipelago folder', self.ap), ('Game YAML folder', self.games), ('Output folder', self.output)]:
            self.path_row(frame, label, variable)
        self.install_button = ttk.Button(frame, text='Install Roster world', command=self.install)
        self.install_button.pack(anchor='w', pady=8)
        ttk.Label(frame, text='Put one configured YAML per candidate game in your game folder.').pack(anchor='w')
        choices = ttk.Frame(frame)
        choices.pack(fill='x', pady=10)
        for label, variable, width in [('Games to pick', self.pick, 7), ('Starting games', self.start, 7), ('Seed (optional)', self.seed, 16)]:
            cell = ttk.Frame(choices)
            cell.pack(side='left', padx=(0, 20))
            ttk.Label(cell, text=label).pack(anchor='w')
            entry = ttk.Entry(cell, textvariable=variable, width=width)
            entry.pack(anchor='w')
            self.inputs.append(entry)
        self.generate_button = ttk.Button(frame, text='Generate seed', command=self.generate)
        self.generate_button.pack(anchor='w', pady=8)
        self.status = tk.StringVar(value='Ready. Selected game names stay hidden until unlocked.')
        ttk.Label(frame, textvariable=self.status, wraplength=730).pack(anchor='w', pady=(4, 8))
        self.reveal = tk.Text(frame, height=8, wrap='word', font=('Segoe UI', 10), state='disabled')
        self.reveal.pack(fill='both', expand=True)
        actions = ttk.Frame(frame)
        actions.pack(fill='x', pady=8)
        ttk.Button(actions, text='Open output folder', command=self.open_output).pack(side='left')
        ttk.Button(actions, text='Host on Archipelago', command=self.open_host).pack(side='left', padx=8)
        ttk.Separator(frame).pack(fill='x', pady=8)
        connect = ttk.Frame(frame)
        connect.pack(fill='x')
        ttk.Label(connect, text='Room address').pack(side='left')
        ttk.Entry(connect, textvariable=self.server).pack(side='left', fill='x', expand=True, padx=8)
        ttk.Button(connect, text='Start Roster client', command=self.start_client).pack(side='right')
        ttk.Label(frame, text='Use host:port or wss://host:port. The client connects as Roster.').pack(anchor='w', pady=5)
        tracker = ttk.Frame(frame)
        tracker.pack(fill='x', pady=5)
        ttk.Label(tracker, text='Tracker slot').pack(side='left')
        ttk.Entry(tracker, textvariable=self.tracker_slot, width=16).pack(side='left', padx=8)
        ttk.Button(tracker, text='Start gated tracker (source only)', command=self.start_tracker).pack(side='left')
        ttk.Label(frame, text='Gated tracking requires a Universal Tracker source setup; stock installer UT is not gated.').pack(anchor='w')
        root.after(100, self.poll)

    def path_row(self, parent, label, variable):
        from tkinter import ttk, filedialog
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=4)
        ttk.Label(row, text=label, width=20).pack(side='left')
        entry = ttk.Entry(row, textvariable=variable)
        entry.pack(side='left', fill='x', expand=True, padx=(0, 8))
        def browse():
            path = filedialog.askdirectory(initialdir=variable.get() or str(APP_DIR))
            if path:
                variable.set(path)
        button = ttk.Button(row, text='Browse…', command=browse)
        button.pack(side='right')
        self.inputs.extend([entry, button])

    def install(self):
        from tkinter import messagebox
        try:
            self.status.set(install_world(self.ap.get()))
        except Exception as exc:
            messagebox.showerror('Roster installation', str(exc))

    def set_busy(self, busy):
        self.busy = busy
        for widget in [self.generate_button, self.install_button, *self.inputs]:
            widget.configure(state='disabled' if busy else 'normal')

    def generate(self):
        from tkinter import messagebox
        if self.busy:
            return
        try:
            pick, start = int(self.pick.get()), int(self.start.get())
            if not 1 <= start <= min(pick, 20):
                raise ValueError('Choose 1–20 starting games, no more than the number picked.')
            games = Path(self.games.get()).resolve()
            count = sum(p.suffix.lower() in ('.yaml', '.yml') for p in games.iterdir() if p.is_file())
            if not 1 <= pick <= count:
                raise ValueError(f'Choose between 1 and {count} games from this folder.')
            ap = Path(self.ap.get()).resolve()
            if not ((ap / 'Generate.py').is_file() or (ap / 'ArchipelagoGenerate.exe').is_file()):
                raise ValueError('Select the Archipelago installation folder first.')
            if getattr(sys, 'frozen', False) and not (ap / 'ArchipelagoGenerate.exe').is_file():
                raise ValueError('The EXE uses the Windows installer. For a source checkout, run python RosterLauncher.py.')
            args = ['--archipelago', str(ap), '--games', str(games), '--pick', str(pick), '--start', str(start), '--outputpath', str(Path(self.output.get()).resolve())]
            if self.seed.get().strip():
                args += ['--seed', str(int(self.seed.get()))]
        except (ValueError, OSError) as exc:
            messagebox.showerror('Check generation settings', str(exc))
            return
        self.set_busy(True)
        self.status.set('Generating… This can take several minutes. Game names remain hidden.')
        self.set_reveal('')
        def run():
            with tempfile.TemporaryDirectory(prefix='roster-launcher-') as temp:
                result_file = Path(temp) / 'result.json'
                try:
                    process = subprocess.run(worker_command('--generate-worker', [*args, '--result-file', str(result_file)]), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    if process.returncode:
                        self.events.put(('failure', process.stdout))
                    else:
                        self.events.put(('success', json.loads(result_file.read_text(encoding='utf-8'))))
                except Exception as exc:
                    self.events.put(('failure', f'{type(exc).__name__}: {exc}'))
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        while not self.events.empty():
            kind, payload = self.events.get_nowait()
            self.set_busy(False)
            if kind == 'success':
                self.result = payload
                self.status.set('Seed generated. Host the ZIP below, then start the Roster client.')
                starts = payload.get('starting_games', [])
                lines = ['Starting games:'] + [f"  {entry['slot']} — {entry['game']}" for entry in starts]
                if not starts:
                    lines.append('  Connect RosterClient after hosting to reveal starting games.')
                lines += ['', f"ZIP: {payload['output']}", f"Tracker YAMLs: {payload.get('tracker_dir', '')}"]
                self.set_reveal('\n'.join(lines))
            else:
                try:
                    out = Path(self.output.get()).resolve()
                    out.mkdir(parents=True, exist_ok=True)
                    log = out / 'roster_launcher_failure.log'
                    log.write_text(payload, encoding='utf-8')
                    detail = f'Details: {log} (may contain spoilers).'
                except OSError:
                    detail = 'Check that the output folder is writable.'
                self.status.set('Generation failed. Check game worlds and dependencies. ' + detail)
        self.root.after(100, self.poll)

    def set_reveal(self, text):
        self.reveal.configure(state='normal')
        self.reveal.delete('1.0', 'end')
        self.reveal.insert('1.0', text)
        self.reveal.configure(state='disabled')

    def open_output(self):
        from tkinter import messagebox
        try:
            Path(self.output.get()).mkdir(parents=True, exist_ok=True)
            os.startfile(str(Path(self.output.get()).resolve()))
        except OSError as exc:
            messagebox.showerror('Open folder', str(exc))

    def open_host(self):
        import webbrowser
        webbrowser.open('https://archipelago.gg/uploads')

    def start_client(self):
        from tkinter import messagebox
        try:
            from RosterStandalone import parse_connection
            address = self.server.get().strip()
            parse_connection(address)
            state_file = str(Path(self.output.get()).resolve() / 'roster-client-state.json')
            subprocess.Popen(worker_command('--client-worker', ['--name', 'Roster', '--connect', address, '--state-file', state_file]), creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0))
        except (OSError, ValueError) as exc:
            messagebox.showerror('Start client', str(exc))

    def close(self):
        from tkinter import messagebox
        if self.busy:
            messagebox.showinfo('Generation is running', 'Wait for generation to finish before closing Roster.')
            return
        self.root.destroy()

    def start_tracker(self):
        from tkinter import messagebox
        if getattr(sys, 'frozen', False):
            messagebox.showinfo('Source tracker required', 'The installer tracker cannot load this bridge. Run python RosterLauncher.py from the repo with an Archipelago source checkout containing Universal Tracker. See docs/tracker-bridge.md.')
            return
        try:
            ap = Path(self.ap.get()).resolve()
            if not (ap / 'CommonClient.py').is_file():
                raise ValueError('Select an Archipelago source checkout containing Universal Tracker.')
            slot = self.tracker_slot.get().strip()
            if not slot:
                raise ValueError('Enter the revealed slot name, such as Game 01.')
            from RosterStandalone import parse_connection
            parse_connection(self.server.get().strip())
            args = [sys.executable, str(RESOURCE_DIR / 'RosterTracker.py'), '--archipelago', str(ap),
                    '--roster-state', str(Path(self.output.get()).resolve() / 'roster-client-state.json'),
                    '--slot', slot, '--connect', self.server.get().strip()]
            subprocess.Popen(args, creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0))
        except (OSError, ValueError) as exc:
            messagebox.showerror('Start tracker', str(exc))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--generate-worker':
        import roster_generate
        return roster_generate.main(sys.argv[2:])
    if len(sys.argv) > 1 and sys.argv[1] == '--client-worker':
        from RosterStandalone import main as client_main
        return client_main(sys.argv[2:])
    if getattr(sys, 'frozen', False) and sys.platform == 'win32':
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    import tkinter as tk
    root = tk.Tk()
    Launcher(root)
    root.mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
