#!/usr/bin/env python3
"""Record real ZedLink controls against isolated native Zed and a scripted demo provider."""
import io
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import ThreadingHTTPServer

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait

import deterministic_model_fixture as model
from test_native_fixture import rpc
from test_native_agent_smoke import until
from test_gateway_transport import BINARY, ROOT, admin, http
from demo_video import DemoVideo


def main():
    if os.environ.get('ZEDLINK_SCREENSHOT_ISOLATED_DISPLAY') != '1' or not os.environ.get('DISPLAY'):
        raise SystemExit('Use the documented separate Xvfb display; never capture the owner desktop.')
    with tempfile.TemporaryDirectory(prefix='zedlink-recording-') as folder:
        root = Path(folder)
        project, profile, probe = root/'Orbit Notes', root/'profile', root/'probe'
        (project/'src').mkdir(parents=True)
        (project/'src/reconnect.py').write_text('''"""Keep retry timing bounded while reconnecting to a saved gateway."""

def retry_delay(attempt):
    return min(2 ** max(0, attempt), 30)
''')
        (project/'test_reconnect.py').write_text('''import unittest
from src.reconnect import retry_delay

class ReconnectTests(unittest.TestCase):
    def test_initial_delay(self):
        self.assertEqual(retry_delay(0), 1)
    def test_backoff(self):
        self.assertEqual(retry_delay(3), 8)
    def test_delay_is_bounded(self):
        self.assertEqual(retry_delay(20), 30)
''')
        (project/'README.md').write_text('# Orbit Notes\nDisposable connection-recovery example.\n')
        subprocess.run(['git','init','-q',str(project)],check=True)
        (profile/'config').mkdir(parents=True); probe.mkdir(mode=0o700)
        class Handler(model.Handler):
            def do_POST(self):
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                messages=payload.get('messages',[])
                index=next((i for i in range(len(messages)-1,-1,-1) if messages[i].get('role')=='user'),-1)
                turn=messages[index:] if index>=0 else []
                prompt=json.dumps(turn[0]) if turn else ''
                has_result=any(item.get('role')=='tool' for item in turn)
                tool=None
                if 'Run the reconnect tests' in prompt and not has_result:
                    tool=('terminal',{'command':'python3 -m unittest -v test_reconnect.py','cd':'.','timeout_ms':10000})
                elif 'Delegate a short review' in prompt and not has_result:
                    tool=('spawn_agent',{'label':'Review reconnect safety','message':'Review the retry policy: delay is 1, 2, 4, 8, 16 and then capped at 30 seconds. Return a concise summary with two bullets.'})
                if has_result:
                    answer='### Tests passed\n\nAll three reconnect tests passed in the project terminal. The retry delay increases gradually and stays capped at **30 seconds**.\n\n' if 'Run the reconnect tests' in prompt else '### Review complete\n\nThe parallel agent checked the retry policy. Open **Agent history** to read its findings without interrupting this conversation.\n\n'
                elif 'Review the retry policy' in prompt:
                    answer='### Reconnect safety review\n\n- **Bounded delay:** retry intervals stop growing at 30 seconds.\n- **Same session:** reconnect to the existing conversation and reconcile delivery before sending again.\n\nThe policy is suitable for a small connection-recovery example.'
                else:
                    answer='### A connection that recovers gracefully\n\nThe project uses exponential backoff: **1, 2, 4, 8, 16, then 30 seconds**.\n\n- Your agent continues working in desktop Zed when this browser disconnects.\n- Reconnecting restores the same exposed conversation.\n- Pending permissions remain under your control.\n\nOpen **Workspace** to inspect `src/reconnect.py`, or ask me to run its tests.'
                self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.send_header('Connection','close'); self.end_headers()
                def event(delta,finish=None):
                    self.wfile.write(b'data: '+json.dumps({'choices':[{'index':0,'delta':delta,'finish_reason':finish}]}).encode()+b'\n\n'); self.wfile.flush()
                try:
                    if tool:
                        event({'tool_calls':[{'index':0,'id':'demo-'+str(time.time_ns()),'type':'function','function':{'name':tool[0],'arguments':json.dumps(tool[1])}}]}); event({},'tool_calls')
                    else:
                        for word in answer.split(' '): event({'content':word+' '}); time.sleep(.09)
                        event({},'stop')
                    self.wfile.write(b'data: [DONE]\n\n'); self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError): pass
        provider=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=provider.serve_forever,daemon=True).start()
        settings={'zedlink':{'allow_session_creation':True,'start_gateway_on_launch':False},
            'telemetry':{'metrics':False,'diagnostics':False},'session':{'trust_all_worktrees':True},
            'agent':{'notify_when_agent_waiting':'never','enable_feedback':False,'default_profile':'write','default_model':{'provider':'openai','model':'zedlink-fixture'},'tool_permissions':{'default':'confirm'}},
            'language_models':{'openai':{'api_url':f'http://127.0.0.1:{provider.server_port}/v1','available_models':[{'name':'zedlink-fixture','display_name':'Demo provider','max_tokens':131072,'max_output_tokens':2048,'capabilities':{'chat_completions':True,'images':False}}]}}}
        (profile/'config/settings.json').write_text(json.dumps(settings))
        env={k:v for k,v in os.environ.items() if not k.startswith('ZEDLINK_') and k not in ('WAYLAND_DISPLAY','OPENAI_API_KEY','ANTHROPIC_API_KEY')}
        env.update(ZED_RELEASE_CHANNEL='dev',ZED_ALLOW_EMULATED_GPU='1',OPENAI_API_KEY='disposable-demo',ZEDLINK_PROBE_DIR=str(probe),ZEDLINK_PROBE_PROJECT_ROOT=str(project))
        zed=gateway=browser=video=None
        try:
            with (root/'zed.log').open('w') as log:
                zed=subprocess.Popen([str(ROOT/'zed-source/target/debug/zed'),'--user-data-dir',str(profile),str(project)],cwd=ROOT/'zed-source',env=env,stdout=log,stderr=log)
                sock=str(probe/'zedlink.sock'); until(lambda: Path(sock).exists())
                info=rpc(sock,'instance.info',{}); base={'instance_id':info['instance_id'],'epoch':info['epoch']}
                def create(title):
                    request = str(uuid.uuid4())
                    def action():
                        try: return rpc(sock,'thread.create',{**base,'title':title},request).get('thread_id')
                        except RuntimeError as error:
                            if 'INSTANCE_UNAVAILABLE' in str(error): return None
                            raise
                    return until(action)
                thread=create('Orbit Notes · reconnect review'); secondary=create('Orbit Notes · release checklist')
                cert,key,state=root/'cert.pem',root/'key.pem',root/'gateway'
                subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); key.chmod(0o600)
                with socket.socket() as candidate: candidate.bind(('127.0.0.1',0)); port=candidate.getsockname()[1]
                url=f'https://localhost:{port}'; tls=ssl.create_default_context(cafile=str(cert))
                gateway=subprocess.Popen([str(BINARY),'serve',f'127.0.0.1:{port}',str(cert),str(key),sock,str(state)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                def gateway_ready():
                    try: return http(url,tls,'/v1/gateway')[1]
                    except OSError: return None
                identity=until(gateway_ready)
                options=Options(); options.add_argument('-kiosk'); options.accept_insecure_certs=True; options.set_preference('network.proxy.type',0); options.set_preference('permissions.default.persistent-storage',1)
                browser=webdriver.Firefox(service=Service('/usr/bin/geckodriver'),options=options)
                browser.set_window_size(1280,800); browser.get(url+'/#gateway='+identity['gateway_id'])
                wait=WebDriverWait(browser,30)
                wait.until(lambda d:d.find_element(By.ID,'pair-code').is_displayed())
                browser.find_element(By.ID,'pair-code').send_keys(admin(state,'pair-short-code')['code']); browser.find_element(By.ID,'pair-button').click()
                wait.until(lambda d:len(d.find_elements(By.CSS_SELECTOR,'.thread-item'))==2)
                wait.until(lambda d:d.find_element(By.ID,'show-actions').is_enabled())
                wait.until(lambda d:'live updates' in d.find_element(By.ID,'connection').text)
                browser.find_element(By.CSS_SELECTOR,f'.thread-item[data-thread-id="{secondary}"]').click()
                wait.until(lambda d:d.find_element(By.ID,'thread-title').text=='Orbit Notes · release checklist')
                wait.until(lambda d:'live updates' in d.find_element(By.ID,'connection').text)
                # Record only the isolated kiosk after pairing; no codes, OS chrome or native desktop.
                subprocess.run(['xdotool','search','--onlyvisible','--class','firefox','windowsize','1280','800'],check=True,stdout=subprocess.DEVNULL)
                video=DemoVideo(ROOT/'assets/recordings',browser,width=1280,height=800,fps=60)
                video.chapter('Choose a conversation')
                video.scene(2)
                video.click(browser,browser.find_element(By.CSS_SELECTOR,f'.thread-item[data-thread-id="{thread}"]'))
                wait.until(lambda d:d.find_element(By.ID,'thread-title').text=='Orbit Notes · reconnect review'); video.scene(2)
                video.chapter('Send a prompt to the same Zed agent')
                video.click(browser,browser.find_element(By.ID,'prompt')); video.type(browser.find_element(By.ID,'prompt'),'Explain how this project reconnects safely.')
                video.click(browser,browser.find_element(By.ID,'send'))
                video.chapter('Follow the response as it streams')
                wait.until(lambda d:'run its tests' in d.find_element(By.ID,'transcript-entries').text); video.scene(3)
                video.chapter('Browse the project and read a file')
                video.click(browser,browser.find_element(By.ID,'show-context'))
                wait.until(lambda d:d.find_elements(By.CSS_SELECTOR,'#file-list [data-path="src"]'))
                video.click(browser,browser.find_element(By.CSS_SELECTOR,'#file-list [data-path="src"]'))
                wait.until(lambda d:d.find_elements(By.CSS_SELECTOR,'#file-list [data-path="src/reconnect.py"]'))
                video.click(browser,browser.find_element(By.CSS_SELECTOR,'#file-list [data-path="src/reconnect.py"]')); video.scene(4)
                video.click(browser,browser.find_element(By.ID,'close-context'))
                video.chapter('Approve a command before it runs')
                video.click(browser,browser.find_element(By.ID,'prompt')); video.type(browser.find_element(By.ID,'prompt'),'Run the reconnect tests for this project.')
                video.click(browser,browser.find_element(By.ID,'send'))
                wait.until(lambda d:d.find_elements(By.CSS_SELECTOR,'#approvals .primary')); video.scene(3)
                video.click(browser,browser.find_element(By.CSS_SELECTOR,'#approvals .primary'))
                wait.until(lambda d:'All three reconnect tests passed' in d.find_element(By.ID,'transcript-entries').text); video.scene(3)
                native=rpc(sock,'thread.snapshot',{'thread_id':thread})
                assert any('Ran 3 tests' in entry or 'test_delay_is_bounded' in entry for entry in native['entries_markdown']), 'Real native terminal must report project tests'
                video.chapter('Delegate work to a parallel agent')
                video.click(browser,browser.find_element(By.ID,'prompt')); video.type(browser.find_element(By.ID,'prompt'),'Delegate a short review of the reconnect policy.')
                video.click(browser,browser.find_element(By.ID,'send'))
                wait.until(lambda d:d.find_elements(By.CSS_SELECTOR,'.subagent.active summary'))
                video.click(browser,browser.find_element(By.CSS_SELECTOR,'.subagent.active summary'))
                wait.until(lambda d:'Reconnect safety review' in d.find_element(By.CSS_SELECTOR,'.subagent[open] .subagent-entries').text); video.scene(3)
                video.click(browser,browser.find_element(By.CSS_SELECTOR,'.subagent[open] .subagent-controls button'))
                wait.until(lambda d:'Review complete' in d.find_element(By.ID,'transcript-entries').text)
                video.chapter('Revisit completed work in Agent history')
                video.click(browser,browser.find_element(By.ID,'show-actions')); video.click(browser,browser.find_element(By.ID,'action-agent-history')); video.scene(2)
                video.click(browser,browser.find_element(By.CSS_SELECTOR,'.agent-history-row')); video.scene(4)
                video.click(browser,browser.find_element(By.CSS_SELECTOR,'.subagent[open] .subagent-controls button'))
                video.chapter('Keep the conversation moving'); video.scene(3)
                (ROOT/'assets/recordings/native-demo-evidence.json').write_text(json.dumps({'native_thread':True,'native_terminal_tests':3,'native_child_history':True,'provider':'scripted loopback demo','owner_workspace_used':False},indent=2)+'\n')
        finally:
            try:
                if video: video.close()
            finally:
                if browser: browser.quit()
                for process in (gateway,zed):
                    if process:
                        process.terminate()
                        try: process.wait(timeout=10)
                        except subprocess.TimeoutExpired: process.kill(); process.wait()
                provider.shutdown(); provider.server_close()

if __name__=='__main__': main()
