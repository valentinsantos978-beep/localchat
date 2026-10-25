import os, sys, json, threading, subprocess, base64, time
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.core.clipboard import Clipboard
from kivy.clock import Clock
import requests

# ============================================================
# Ponte Termux (só para /run, /ls, /read, /write)
# ============================================================
BRIDGE_SCRIPT = r'''
import http.server, socketserver, json, os, subprocess, threading
class H(http.server.BaseHTTPRequestHandler):
    def _j(self, d, s=200):
        self.send_response(s); self.send_header('Content-Type','application/json'); self.end_headers()
        self.wfile.write(json.dumps(d).encode())
    def do_GET(self):
        if self.path == '/ping':
            self._j({'status':'ok','service':'termux-bridge'})
        else:
            self._j({'error':'not found'}, 404)
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(n)) if n else {}
        if self.path == '/run':
            try:
                r = subprocess.run(body.get('cmd','echo'), shell=True, capture_output=True, text=True, timeout=120)
                self._j({'stdout': r.stdout, 'stderr': r.stderr, 'code': r.returncode})
            except Exception as e: self._j({'error': str(e)}, 500)
        elif self.path == '/ls':
            try:
                p = body.get('path','.')
                items = [{'name': e.name, 'dir': e.is_dir(), 'path': e.path} for e in os.scandir(p)]
                self._j({'entries': items})
            except Exception as e: self._j({'error': str(e)}, 500)
        elif self.path == '/read':
            try:
                self._j({'content': open(body['path'], errors='ignore').read(50000)})
            except Exception as e: self._j({'error': str(e)}, 500)
        elif self.path == '/write':
            try:
                open(body['path'],'w').write(body.get('content',''))
                self._j({'status':'ok'})
            except Exception as e: self._j({'error': str(e)}, 500)
        else:
            self._j({'error':'not found'}, 404)
    def log_message(self, *a): pass
if __name__ == '__main__':
    port = int(os.environ.get('BRIDGE_PORT','8080'))
    srv = socketserver.ThreadingTCPServer(('127.0.0.1', port), H)
    srv.daemon_threads = True
    print('Bridge on', port)
    srv.serve_forever()
'''

def build_bridge_command():
    b64 = base64.b64encode(BRIDGE_SCRIPT.encode()).decode()
    payload = "import base64;exec(base64.b64decode('" + b64 + "').decode())"
    return ('am startservice --user 0 -n com.termux/com.termux.app.RunCommandService '
            '-a com.termux.RUN_COMMAND '
            '--es com.termux.RUN_COMMAND_PATH /data/data/com.termux/files/usr/bin/python '
            '--esa com.termux.RUN_COMMAND_ARGUMENTS - '
            '--es com.termux.RUN_COMMAND_STDIN "' + payload + '" '
            '--ez com.termux.RUN_COMMAND_BACKGROUND false')

def bridge_ok():
    try:
        return requests.get('http://127.0.0.1:8080/ping', timeout=1.5).status_code == 200
    except Exception:
        return False

# ============================================================
# Diretórios e llama-server
# ============================================================
def get_app_dir():
    try:
        from android.storage import app_storage_path
        return app_storage_path()
    except Exception:
        return os.path.dirname(os.path.abspath(__file__))

def get_bin_dir():
    d = os.path.join(get_app_dir(), 'bin')
    os.makedirs(d, exist_ok=True)
    return d

def get_config_path():
    return os.path.join(get_app_dir(), 'config.json')

def load_config():
    try:
        with open(get_config_path()) as f: return json.load(f)
    except Exception: return {}

def save_config(c):
    try:
        with open(get_config_path(),'w') as f: json.dump(c, f)
    except Exception: pass

def extract_llama_server():
    target = os.path.join(get_bin_dir(), 'llama-server')
    try:
        if os.path.exists(target) and os.path.getsize(target) > 500000:
            os.chmod(target, 0o700)
            return target
    except Exception: pass
    try:
        from android import mActivity
        if mActivity is None: return None
        assets = mActivity.getApplicationContext().getAssets()
        inp = assets.open('llama-server')
        with open(target, 'wb') as f:
            buf = bytearray(65536)
            while True:
                n = inp.read(buf)
                if n <= 0: break
                f.write(buf[:n])
        inp.close()
        os.chmod(target, 0o700)
        return target
    except Exception as e:
        print('extract_llama_server:', e)
        return None

class LlamaServer:
    def __init__(self, port=8090):
        self.port = port
        self.proc = None
        self.model = None
    def running(self):
        return self.proc is not None and self.proc.poll() is None
    def ready(self):
        try:
            return requests.get('http://127.0.0.1:%d/health' % self.port, timeout=1).status_code == 200
        except Exception:
            return False
    def start(self, model_path):
        self.stop()
        server = extract_llama_server()
        if not server:
            raise RuntimeError('llama-server indisponivel (asset ausente)')
        env = dict(os.environ)
        env['LD_LIBRARY_PATH'] = get_bin_dir()
        args = [server, '-m', model_path, '--host', '127.0.0.1', '--port', str(self.port),
                '-c', '4096', '-t', '4']
        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        for _ in range(180):
            if self.proc.poll() is not None:
                raise RuntimeError('llama-server encerrou (codigo %s)' % self.proc.returncode)
            if self.ready():
                self.model = model_path
                return True
            time.sleep(1)
        raise RuntimeError('timeout ao carregar o modelo')
    def stop(self):
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try: self.proc.kill()
                except Exception: pass
            self.proc = None
        self.model = None

LLAMA = LlamaServer(8090)

def stream_local(messages, cancel_flag):
    r = requests.post('http://127.0.0.1:%d/v1/chat/completions' % LLAMA.port,
                      json={'messages': messages, 'stream': True, 'max_tokens': 2048},
                      stream=True, timeout=900)
    for line in r.iter_lines(decode_unicode=True):
        if cancel_flag and cancel_flag(): break
        if line and line.startswith('data: '):
            data = line[6:]
            if data == '[DONE]': break
            try:
                obj = json.loads(data)
                ch = obj.get('choices', [{}])[0]
                d = ch.get('delta', {})
                if d.get('reasoning_content'):
                    yield ('reasoning', d['reasoning_content'])
                if d.get('content'):
                    yield ('content', d['content'])
            except Exception:
                pass

# ============================================================
# Popups
# ============================================================
class PopupConexao(Popup):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.title = 'Conectar ao Termux'
        self.size_hint = (0.92, 0.78)
        self.auto_dismiss = False
        root = BoxLayout(orientation='vertical', spacing=8, padding=10)
        info = Label(text='Voce pediu um comando de shell, mas o Termux nao esta conectado.\nCopie o comando abaixo e cole no Termux (ou toque Conectar Automatico).\nA IA continua funcionando sem o Termux.', halign='center', valign='middle')
        info.bind(size=lambda *_: setattr(info, 'text_size', (info.width, None)))
        root.add_widget(info)
        for label, cb in [('Copiar Comando', self.copiar),
                          ('Verificar Conexao', self.verificar),
                          ('Conectar Automatico', self.conectar),
                          ('Fechar', lambda *_: self.dismiss())]:
            b = Button(text=label, size_hint=(1, 0.15))
            b.bind(on_release=cb)
            root.add_widget(b)
        self.content = root
    def copiar(self, inst):
        Clipboard.copy(build_bridge_command())
        inst.text = 'Copiado!'
    def verificar(self, inst):
        if bridge_ok():
            inst.text = 'Conectado!'
            Clock.schedule_once(lambda *_: self.dismiss(), 1)
        else:
            inst.text = 'Ainda desconectado'
    def conectar(self, inst):
        try:
            b64 = base64.b64encode(BRIDGE_SCRIPT.encode()).decode()
            payload = "import base64;exec(base64.b64decode('" + b64 + "').decode())"
            subprocess.run([
                'am','startservice','--user','0',
                '-n','com.termux/com.termux.app.RunCommandService',
                '-a','com.termux.RUN_COMMAND',
                '--es','com.termux.RUN_COMMAND_PATH','/data/data/com.termux/files/usr/bin/python',
                '--esa','com.termux.RUN_COMMAND_ARGUMENTS','-',
                '--es','com.termux.RUN_COMMAND_STDIN', payload,
                '--ez','com.termux.RUN_COMMAND_BACKGROUND','false'
            ], check=True, timeout=15)
            inst.text = 'Comando enviado!'
        except Exception as e:
            inst.text = 'Falha: ' + str(e)[:40]

class PopupModelos(Popup):
    def __init__(self, on_pick, **kw):
        super().__init__(**kw)
        self.on_pick = on_pick
        self.title = 'Selecione um modelo GGUF'
        self.size_hint = (0.95, 0.85)
        self.auto_dismiss = False
        root = BoxLayout(orientation='vertical', spacing=6, padding=8)
        self.status = Label(text='Procurando em /sdcard/Download/...', size_hint=(1, None), height=40)
        root.add_widget(self.status)
        scroll = ScrollView()
        self.lista = BoxLayout(orientation='vertical', size_hint_y=None, spacing=4)
        self.lista.bind(minimum_height=self.lista.setter('height'))
        scroll.add_widget(self.lista)
        root.add_widget(scroll)
        close = Button(text='Fechar', size_hint=(1, None), height=50)
        close.bind(on_release=lambda *_: self.dismiss())
        root.add_widget(close)
        self.content = root
        Clock.schedule_once(lambda *_: self.scan(), 0.2)
    def scan(self):
        self.lista.clear_widgets()
        paths = ['/sdcard/Download', '/storage/emulated/0/Download']
        found = []
        for base in paths:
            try:
                for name in sorted(os.listdir(base)):
                    if name.lower().endswith('.gguf'):
                        found.append(os.path.join(base, name))
            except Exception:
                continue
        if not found:
            self.status.text = 'Nenhum .gguf encontrado em /sdcard/Download/.'
            return
        self.status.text = '%d modelo(s) encontrado(s)' % len(found)
        for p in found:
            try:
                mb = os.path.getsize(p) // (1024*1024)
            except Exception:
                mb = 0
            b = Button(text=os.path.basename(p) + '  (%d MB)' % mb,
                       size_hint_y=None, height=44)
            b.bind(on_release=lambda inst, path=p: self.pick(path))
            self.lista.add_widget(b)
    def pick(self, path):
        self.dismiss()
        self.on_pick(path)

# ============================================================
# Chat
# ============================================================
class ChatUI(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation='vertical', **kw)
        self.messages = []
        self.cancel = False

        top = BoxLayout(size_hint=(1, None), height=44, spacing=6, padding=(6,4))
        self.status = Label(text='Iniciando...', halign='left', valign='middle')
        self.status.bind(size=lambda *_: setattr(self.status, 'text_size', (self.status.width, None)))
        top.add_widget(self.status)
        bmodel = Button(text='Modelo', size_hint=(None, 1), width=90)
        bmodel.bind(on_release=lambda *_: self.pick_model())
        top.add_widget(bmodel)
        self.add_widget(top)

        self.scroll = ScrollView()
        self.log = Label(text='', size_hint_y=None, halign='left', valign='top', markup=True)
        self.log.bind(width=lambda *_: setattr(self.log, 'text_size', (self.log.width, None)))
        self.log.bind(texture_size=lambda *_: setattr(self.log, 'height', self.log.texture_size[1]))
        self.scroll.add_widget(self.log)
        self.add_widget(self.scroll)

        bar = BoxLayout(size_hint=(1, None), height=56, spacing=6, padding=(6,6))
        self.entry = TextInput(hint_text='Mensagem ou /run, /ls, /read...', multiline=False)
        self.entry.bind(on_text_validate=self.send)
        bar.add_widget(self.entry)
        btn = Button(text='Enviar', size_hint=(None, 1), width=90)
        btn.bind(on_release=self.send)
        bar.add_widget(btn)
        self.add_widget(bar)

    def update_status(self):
        parts = []
        if LLAMA.running() and LLAMA.ready():
            parts.append('IA local: ' + os.path.basename(LLAMA.model or '?'))
        elif LLAMA.running():
            parts.append('IA local: carregando...')
        else:
            parts.append('IA local: parada')
        parts.append('Termux: ' + ('ok' if bridge_ok() else 'off'))
        self.status.text = ' | '.join(parts)

    def append(self, txt):
        self.log.text += txt + '\n'

    def pick_model(self):
        def on_pick(path):
            cfg = load_config()
            cfg['last_model'] = path
            save_config(cfg)
            threading.Thread(target=self.load_model, args=(path,), daemon=True).start()
        PopupModelos(on_pick).open()

    def load_model(self, path):
        Clock.schedule_once(lambda *_: self.append('[color=888888]Carregando modelo...[/color]'))
        try:
            LLAMA.start(path)
            Clock.schedule_once(lambda *_: self.append('[color=00ff88]Modelo carregado: ' + os.path.basename(path) + '[/color]'))
        except Exception as e:
            Clock.schedule_once(lambda *_: self.append('[color=ff0000]Erro ao carregar: ' + str(e) + '[/color]'))
        Clock.schedule_once(lambda *_: self.update_status())

    def send(self, *_):
        msg = self.entry.text.strip()
        if not msg: return
        self.entry.text = ''
        self.append('[color=00aaff]Voce:[/color] ' + msg)
        self.messages.append({'role': 'user', 'content': msg})
        threading.Thread(target=self.handle, args=(msg,), daemon=True).start()

    def handle(self, msg):
        try:
            if msg.startswith('/run '):
                if not bridge_ok():
                    Clock.schedule_once(lambda *_: PopupConexao().open())
                    return
                r = requests.post('http://127.0.0.1:8080/run', json={'cmd': msg[5:]}, timeout=120)
                self.append('[color=ffaa00]Shell:[/color] ' + json.dumps(r.json(), indent=2)[:3000])
                return
            if msg.startswith('/ls'):
                if not bridge_ok():
                    Clock.schedule_once(lambda *_: PopupConexao().open())
                    return
                p = msg[3:].strip() or '.'
                r = requests.post('http://127.0.0.1:8080/ls', json={'path': p}, timeout=30)
                j = r.json()
                if 'entries' in j:
                    for e in j['entries'][:80]:
                        self.append(('[DIR] ' if e['dir'] else '      ') + e['name'])
                else:
                    self.append(str(j))
                return
            if msg.startswith('/read '):
                if not bridge_ok():
                    Clock.schedule_once(lambda *_: PopupConexao().open())
                    return
                r = requests.post('http://127.0.0.1:8080/read', json={'path': msg[6:].strip()}, timeout=30)
                self.append(str(r.json().get('content', r.json()))[:3000])
                return

            if not (LLAMA.running() and LLAMA.ready()):
                Clock.schedule_once(lambda *_: self.append('[color=888888]Modelo nao carregado. Toque em "Modelo" para escolher um .gguf.[/color]'))
                return

            self.append('[color=00ff88]IA:[/color] ')
            cancel = lambda: False
            for kind, text in stream_local(self.messages, cancel):
                if kind == 'reasoning':
                    Clock.schedule_once(lambda *_, t=text: setattr(self.log, 'text', self.log.text + '[color=888888]' + t + '[/color]'))
                else:
                    Clock.schedule_once(lambda *_, t=text: setattr(self.log, 'text', self.log.text + t))
            self.append('')
        except Exception as e:
            self.append('[color=ff0000]Erro: ' + str(e) + '[/color]')
        finally:
            Clock.schedule_once(lambda *_: self.update_status())

class LocalChatApp(App):
    def build(self):
        ui = ChatUI()
        self.ui = ui

        def boot(dt):
            server = extract_llama_server()
            if server:
                Clock.schedule_once(lambda *_: ui.append('[color=888888]llama-server pronto em ' + server + '[/color]'))
            else:
                Clock.schedule_once(lambda *_: ui.append('[color=ff0000]llama-server nao encontrado nos assets do APK (IA local desativada).[/color]'))

            Clock.schedule_once(lambda *_: ui.update_status())

            cfg = load_config()
            last = cfg.get('last_model')
            if last and os.path.exists(last):
                threading.Thread(target=ui.load_model, args=(last,), daemon=True).start()
            else:
                Clock.schedule_once(lambda *_: ui.append('[color=888888]Toque em "Modelo" e escolha um .gguf em /sdcard/Download/.[/color]'))

            def tick(dt):
                ui.update_status()
            Clock.schedule_interval(tick, 5)

        Clock.schedule_once(boot, 0.5)
        return ui

if __name__ == '__main__':
    LocalChatApp().run()
