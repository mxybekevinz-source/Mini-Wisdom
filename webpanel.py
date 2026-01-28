from flask import Flask, render_template_string, request, jsonify
import threading
import json
import time
import sys
import os

class WebPanel:
    def __init__(self, api_client, bot_instance, host='127.0.0.1', port=5000):
        self.api = api_client
        self.bot = bot_instance
        self.host = host
        self.port = port
        self.app = Flask(__name__)
        self.command_history = []
        self.setup_routes()
    
    def setup_routes(self):
        @self.app.route('/')
        def index():
            return render_template_string("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Wisdom Mini - Web Panel</title>
                <style>
                    body { font-family: Arial; background: #1e1e1e; color: white; margin: 20px; }
                    .container { max-width: 1200px; margin: 0 auto; }
                    .card { background: #2d2d2d; padding: 20px; margin: 10px 0; border-radius: 8px; }
                    .btn { background: #5865f2; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; }
                    .btn:hover { background: #4752c4; }
                    input, textarea { width: 100%; padding: 10px; margin: 5px 0; background: #3d3d3d; color: white; border: 1px solid #555; border-radius: 4px; }
                    .log { background: black; padding: 10px; border-radius: 4px; font-family: monospace; height: 200px; overflow-y: auto; }
                    .status { color: #4caf50; }
                    .error { color: #f44336; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Wisdom Mini Web Panel</h1>
                    
                    <div class="card">
                        <h3>Bot Status</h3>
                        <p class="status">● Connected as: {{ username }}</p>
                        <p>User ID: {{ user_id }}</p>
                    </div>
                    
                    <div class="card">
                        <h3>Execute Command</h3>
                        <form onsubmit="executeCommand(); return false;">
                            <input type="text" id="command" placeholder="Enter command (e.g., +help)" autocomplete="off">
                            <input type="text" id="channel_id" placeholder="Channel ID (optional)">
                            <button type="submit" class="btn">Execute</button>
                        </form>
                    </div>
                    
                    <div class="card">
                        <h3>Quick Actions</h3>
                        <button class="btn" onclick="quickAction('+help')">Show Help</button>
                        <button class="btn" onclick="quickAction('+guilds')">List Guilds</button>
                        <button class="btn" onclick="quickAction('+ms')">Test Latency</button>
                        <button class="btn" onclick="location.reload()">Refresh</button>
                    </div>
                    
                    <div class="card">
                        <h3>Command History</h3>
                        <div class="log" id="history">
                            {% for cmd in history %}
                            <div>[{{ cmd.time }}] {{ cmd.command }}</div>
                            {% endfor %}
                        </div>
                    </div>
                </div>
                
                <script>
                    function executeCommand() {
                        const command = document.getElementById('command').value;
                        const channelId = document.getElementById('channel_id').value;
                        
                        fetch('/execute', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({command: command, channel_id: channelId})
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.success) {
                                alert('Command executed!');
                                document.getElementById('command').value = '';
                                location.reload();
                            } else {
                                alert('Error: ' + data.error);
                            }
                        });
                    }
                    
                    function quickAction(cmd) {
                        document.getElementById('command').value = cmd;
                        executeCommand();
                    }
                </script>
            </body>
            </html>
            """, username=self.api.user_data.get("username", "Unknown") if self.api.user_data else "Unknown",
               user_id=self.api.user_id or "Unknown",
               history=self.command_history[-10:])
        
        @self.app.route('/execute', methods=['POST'])
        def execute():
            data = request.json
            command = data.get('command', '').strip()
            channel_id = data.get('channel_id', '')
            
            if not command:
                return jsonify({"success": False, "error": "No command provided"})
            
            if not channel_id:
                channel_id = self._get_default_channel()
            
            if not channel_id:
                return jsonify({"success": False, "error": "No channel available"})
            
            try:
                fake_ctx = {
                    "message": {"id": "web_" + str(time.time()), "author": {"id": self.api.user_id}},
                    "channel_id": channel_id,
                    "author_id": self.api.user_id,
                    "api": self.api,
                    "bot": self.bot
                }
                
                if command.startswith('+'):
                    parts = command[1:].strip().split()
                    if parts:
                        cmd_name = parts[0].lower()
                        args = parts[1:] if len(parts) > 1 else []
                        self.bot.run_command(cmd_name, fake_ctx, args)
                
                self.command_history.append({
                    "time": time.strftime("%H:%M:%S"),
                    "command": command,
                    "channel": channel_id
                })
                
                return jsonify({"success": True})
            except Exception as e:
                return jsonify({"success": False, "error": str(e)})
        
        @self.app.route('/status')
        def status():
            return jsonify({
                "connected": self.bot.identified,
                "username": self.api.user_data.get("username") if self.api.user_data else None,
                "user_id": self.api.user_id,
                "guild_count": len(self.api.get_guilds()),
                "uptime": "Online" if self.bot.running else "Offline"
            })
    
    def _get_default_channel(self):
        try:
            dms_response = self.api.request("GET", "/users/@me/channels")
            if dms_response and dms_response.status_code == 200:
                dms = dms_response.json()
                if dms:
                    return dms[0]["id"]
            
            guilds = self.api.get_guilds()
            if guilds:
                for guild in guilds:
                    channels = self.api.get_channels(guild["id"])
                    if channels:
                        return channels[0]["id"]
        except:
            pass
        return None
    
    def start(self):
        print(f"[WebPanel] Starting web interface at http://{self.host}:{self.port}")
        threading.Thread(target=lambda: self.app.run(
            host=self.host, 
            port=self.port,
            debug=False,
            use_reloader=False
        ), daemon=True).start()