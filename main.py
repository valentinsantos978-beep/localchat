import os, sys, json, threading, subprocess, base64
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

BRIDGE_SCRIPT = r'''
import http.server, socketserver, json, os, subprocess, threading, base64, sys
try:
    from llama_cpp import Llama
except Exception:
    Llama = None

_state = {'llm': None, 'path': None}
_lock = threading.Lock()

def load_model(path):
    with _lock:
        _state['llm'] = Llama(model_path=path, n_ctx=4096, n_threads=4, verbose=False)
        _state['path'] = path

class H(http.server.BaseHTTPRequestHandler):
    def _j(self, d, s=200):
        self.send_response(s)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(d).encode())
    def do_GET(self):
        if self.path == '/ping':
            self._j({'status': 'ok', 'model': _state['path']})
        elif self.path == '/models':
            d = '/sdcard/Download'
            files = sorted(f for f in os.listdir(d) if f.endswith('.gguf')) if os.path.isdir(d) else []
            self._j({'models': files})
        else:
            self._j({'error': 'not found'}, 404)
    def do_POST(self):
        n = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(n)) if n else {}
        if self.path == '/run':
            try:
                r = subprocess.run(body.get('cmd', 'echo'), shell=True, capture_output=True, text=True, timeout=120)
                self._j({'stdout': r.stdout, 'stderr': r.stderr, 'code': r.returncode})
            except Exception as e:
                self._j({'error': str(e)}, 500)
        elif self.path == '/ls':
            try:
                p = body.get('path', '.')
                items = [{'name': e.name, 'dir': e.is_dir(), 'path': e.path} for e in os.scandir(p)]
                self._j({'entries': items})
            except Exception as e:
                self._j({'error': str(e)}, 500)
        elif self.path == '/read':
            try:
                self._j({'content': open(body['path'], errors='ignore').read(50000)})
            except Exception as e:
                self._j({'error': str(e)}, 500)
        elif self.path == '/write':
            try:
                open(body['path'], 'w').write(body.get('content', ''))
                self._j({'status': 'ok'})
            except Exception as e:
                self._j({'error': str(e)}, 500)
        elif self.path == '/load':
            if Llama is None:
                self._j({'error': 'llama-cpp-python nao instalado'}, 500)
                return
            try:
                p = body['path']
                if not p.startswith('/'):
                    p = '/sdcard/Download/' + p
                load_model(p)
                self._j({'status': 'ok', 'model': p})
            except Exception as e:
                self._j({'error': str(e)}, 500)
        elif self.path == '/llm':
            if _state['llm'] is None:
                self._j({'error': 'modelo nao carregado. Use /load nome.gguf'}, 400)
                return
            msg = body.get('message', '')
            system = body.get('system', 'Voce e um agente util. Pode sugerir /run, /ls, /read, /write.')
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            try:
                with _lock:
                    for chunk in _state['llm'].create_chat_completion(
                        messages=[{'role': 'system', 'content': system}, {'role': 'user', 'content': msg}],
                        stream=True, max_tokens=2048):
                        d = chunk['choices'][0]['delta'].get('content', '')
                        if d:
                            self.wfile.write(('data: ' + json.dumps({'t': d}) + '\n\n').encode())
                            self.wfile.flush()
                self.wfile.write(b'data: [DONE]\n\n')
                self.wfile.flush()
            except Exception as e:
                try:
                    self.wfile.write(('data: ' + json.dumps({'err': str(e)}) + '\n\n').encode())
                    self.wfile.flush()
                except Exception:
                    pass
        else:
            self._j({'error': 'not found'}, 404)
    def log_message(self, *a):
        pass

if __name__ == '__main__':
    port = int(os.environ.get('BRIDGE_PORT', '8080'))
    srv = socketserver.ThreadingTCPServer(('127.0.0.1', port), H)
    srv.daemon_threads = True
    print('Bridge on', port)
    srv.serve_forever()
'''

def build_command():
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
        return requests.get('http://127.0.0.1:8080/ping', timeout=2).status_code == 200
    except Exception:
        return False

class PopupConexao(Popup):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.title = 'Conectar ao Termux'
        self.size_hint = (0.92, 0.78)
        self.auto_dismiss = False
        root = BoxLayout(orientation='vertical', spacing=8, padding=10)
        info = Label(text='A ponte com o Termux nao esta ativa.\nCopie o comando abaixo, cole no Termux, ou toque em Conectar Automatico.\nSe falhar, conceda a permissao RUN_COMMAND nas configuracoes do app.', halign='center', valign='middle')
        info.bind(size=lambda *_: setattr(info, 'text_size', (info.width, None)))
        root.add_widget(info)
        for label, cb in [('Copiar Comando', self.copiar), ('Verificar Conexao', self.verificar), ('Conectar Automatico', self.conectar), ('Fechar', lambda *_: self.dismiss())]:
            b = Button(text=label, size_hint=(1, 0.15))
            b.bind(on_release=cb)
            root.add_widget(b)
        self.content = root
    def copiar(self, inst):
        Clipboard.copy(build_command())
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
                'am', 'startservice', '--user', '0',
                '-n', 'com.termux/com.termux.app.RunCommandService',
                '-a', 'com.termux.RUN_COMMAND',
                '--es', 'com.termux.RUN_COMMAND_PATH', '/data/data/com.termux/files/usr/bin/python',
                '--esa', 'com.termux.RUN_COMMAND_ARGUMENTS', '-',
                '--es', 'com.termux.RUN_COMMAND_STDIN', payload,
                '--ez', 'com.termux.RUN_COMMAND_BACKGROUND', 'false'
            ], check=True, timeout=15)
            inst.text = 'Comando enviado!'
        except Exception as e:
            inst.text = 'Falha: ' + str(e)[:40]

class ChatUI(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation='vertical', **kw)
        self.scroll = ScrollView()
        self.log = Label(text='', size_hint_y=None, halign='left', valign='top', markup=True)
        self.log.bind(width=lambda *_: setattr(self.log, 'text_size', (self.log.width, None)))
        self.log.bind(texture_size=lambda *_: setattr(self.log, 'height', self.log.texture_size[1]))
        self.scroll.add_widget(self.log)
        self.add_widget(self.scroll)
        bar = BoxLayout(size_hint=(1, None), height=50)
        self.entry = TextInput(hint_text='Mensagem ou /run cmd, /ls path, /load model.gguf', multiline=False)
        bar.add_widget(self.entry)
        btn = Button(text='Enviar', size_hint=(None, 1), width=100)
        btn.bind(on_release=self.send)
        bar.add_widget(btn)
        self.add_widget(bar)
        self.append('[b]LocalChat[/b] iniciado.')
    def append(self, txt):
        self.log.text += txt + '\n'
    def send(self, *_):
        msg = self.entry.text.strip()
        if not msg: return
        self.entry.text = ''
        self.append('[color=00aaff]Voce:[/color] ' + msg)
        threading.Thread(target=self.handle, args=(msg,), daemon=True).start()
    def handle(self, msg):
        if not bridge_ok():
            Clock.schedule_once(lambda *_: PopupConexao().open())
            return
        try:
            if msg.startswith('/run '):
                r = requests.post('http://127.0.0.1:8080/run', json={'cmd': msg[5:]}, timeout=120)
                self.append('[color=ffaa00]Shell:[/color] ' + json.dumps(r.json(), indent=2)[:3000])
            elif msg.startswith('/ls'):
                p = msg[3:].strip() or '.'
                r = requests.post('http://127.0.0.1:8080/ls', json={'path': p}, timeout=30)
                j = r.json()
                if 'entries' in j:
                    for e in j['entries'][:80]:
                        self.append(('[DIR] ' if e['dir'] else '      ') + e['name'])
                else:
                    self.append(str(j))
            elif msg.startswith('/read '):
                r = requests.post('http://127.0.0.1:8080/read', json={'path': msg[6:].strip()}, timeout=30)
                self.append(str(r.json().get('content', r.json()))[:3000])
            elif msg.startswith('/load '):
                r = requests.post('http://127.0.0.1:8080/load', json={'path': msg[6:].strip()}, timeout=300)
                self.append('Load: ' + str(r.json()))
            else:
                r = requests.post('http://127.0.0.1:8080/llm', json={'message': msg}, stream=True, timeout=900)
                self.append('[color=00ff88]IA:[/color] ')
                for line in r.iter_lines(decode_unicode=True):
                    if line and line.startswith('data: '):
                        data = line[6:]
                        if data == '[DONE]': break
                        try:
                            j = json.loads(data)
                            if 't' in j:
                                Clock.schedule_once(lambda *_, t=j['t']: setattr(self.log, 'text', self.log.text + t))
                            elif 'err' in j:
                                self.append('[color=ff0000]Erro: ' + j['err'] + '[/color]')
                        except Exception:
                            pass
                self.append('')
        except Exception as e:
            self.append('[color=ff0000]Erro: ' + str(e) + '[/color]')

class LocalChatApp(App):
    def build(self):
        ui = ChatUI()
        Clock.schedule_once(lambda *_: (None if bridge_ok() else PopupConexao().open()), 1.5)
        return ui

if __name__ == '__main__':
    LocalChatApp().run()
