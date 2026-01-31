import json
import time
import threading
import subprocess
import os
import sys
import shutil

class HostManager:
    def __init__(self):
        self.active_tokens = {}
        self.processes = {}
        self.lock = threading.Lock()
    
    def can_use_command(self, user_id):
        with self.lock:
            for data in self.active_tokens.values():
                if data["owner"] == user_id:
                    return True
            return True
    
    def host_token(self, owner_id, token_input):
        if not token_input:
            return False, "No token"
        
        token = self._clean_token(token_input)
        if not token:
            return False, "Bad token"
        
        with self.lock:
            for tid, data in self.active_tokens.items():
                if data["token"] == token:
                    return False, "Already hosted"
            
            config_file = f"hosted_{int(time.time())}.json"
            with open(config_file, "w") as f:
                json.dump({"token": token, "prefix": "+"}, f)
            
            process = self._run_their_bot(config_file, token)
            if not process:
                return False, "Start failed"
            
            token_id = str(int(time.time()))
            self.active_tokens[token_id] = {
                "token": token,
                "owner": owner_id,
                "config": config_file
            }
            self.processes[token_id] = process
            
            return True, "Hosting token"
    
    def _clean_token(self, token_input):
        token_input = token_input.strip('"\' ')
        
        if token_input.startswith("{"):
            try:
                data = json.loads(token_input)
                return data.get("token", "")
            except:
                return token_input
        
        return token_input if "." in token_input else ""
    
    def _run_their_bot(self, config_file, token):
        try:
            runner_code = f"""
import sys, os, json, time, subprocess, shutil

temp_dir = "hosted_bot_{{int(time.time())}}"
os.makedirs(temp_dir, exist_ok=True)

for file in os.listdir("."):
    if file.endswith(".py"):
        shutil.copy(file, os.path.join(temp_dir, file))

os.chdir(temp_dir)

main_py_content = ""
with open("main.py", "r") as f:
    main_py_content = f.read()

lines = main_py_content.split('\\n')
new_lines = []

i = 0
while i < len(lines):
    line = lines[i]
    
    if line.strip().startswith('@bot.command(name="host"'):
        i += 2
        continue
    
    if line.strip().startswith('@bot.command(name="stophost"'):
        i += 2
        continue
    
    if line.strip().startswith('@bot.command(name="listhosted"'):
        i += 2
        continue
    
    new_lines.append(line)
    i += 1

with open("main.py", "w") as f:
    f.write('\\n'.join(new_lines))

with open("config.json", "w") as f:
    json.dump({{"token": "{token}", "prefix": "+"}}, f)

subprocess.run([sys.executable, "main.py"])
"""
            
            runner_file = f"runner_{int(time.time())}.py"
            with open(runner_file, "w") as f:
                f.write(runner_code)
            
            process = subprocess.Popen(
                [sys.executable, runner_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            
            threading.Thread(target=self._cleanup, args=(runner_file, config_file, process), daemon=True).start()
            return process
            
        except Exception as e:
            print(f"Host error: {e}")
            return None
    
    def stop_hosting(self, owner_id):
        with self.lock:
            to_stop = []
            for token_id, data in self.active_tokens.items():
                if data["owner"] == owner_id:
                    to_stop.append(token_id)
            
            for token_id in to_stop:
                if token_id in self.processes:
                    try:
                        self.processes[token_id].terminate()
                    except:
                        pass
                    del self.processes[token_id]
                del self.active_tokens[token_id]
            
            return True, f"Stopped {len(to_stop)}" if to_stop else False, "None"
    
    def list_hosted(self, requester_id):
        with self.lock:
            result = []
            for token_id, data in self.active_tokens.items():
                result.append(f"ID: {token_id} (Owner: {data['owner']})")
            return result
    
    def _cleanup(self, runner_file, config_file, process):
        process.wait()
        try:
            if os.path.exists(runner_file):
                os.remove(runner_file)
            if os.path.exists(config_file):
                os.remove(config_file)
        except:
            pass
    
    def cleanup(self):
        with self.lock:
            for token_id in list(self.active_tokens.keys()):
                if token_id in self.processes:
                    try:
                        self.processes[token_id].terminate()
                    except:
                        pass
                del self.active_tokens[token_id]

host_manager = HostManager()
