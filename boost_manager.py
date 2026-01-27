import json
import time
import threading

class BoostManager:
    def __init__(self, api_client):
        self.api = api_client
        self.boosted_servers = {}
        self.available_boosts = 2
        self.last_check = 0
        self.boost_thread = None
        self.running = False
        
    def check_boost_status(self):
        try:
            response = self.api.request("GET", "/users/@me/guilds/premium/subscription-slots")
            if response and response.status_code == 200:
                slots = response.json()
                available = sum(1 for slot in slots if slot.get("cooldown_ends_at") is None)
                self.available_boosts = available
                return available
        except:
            pass
        return 0
    
    def can_boost(self, server_id):
        current_time = time.time()
        if current_time - self.last_check > 300:
            self.check_boost_status()
            self.last_check = current_time
        
        return self.available_boosts > 0
    
    def boost_server(self, server_id):
        if not self.can_boost(server_id):
            return False, "No boosts available"
        
        try:
            response = self.api.request("PUT", f"/guilds/{server_id}/premium/subscriptions")
            if response and response.status_code == 200:
                self.boosted_servers[server_id] = time.time()
                self.available_boosts -= 1
                return True, f"Boosted {server_id}"
        except Exception as e:
            return False, f"Error: {str(e)[:50]}"
        
        return False, "Boost failed"
    
    def transfer_boost(self, from_server_id, to_server_id):
        try:
            response = self.api.request("DELETE", f"/guilds/{from_server_id}/premium/subscriptions")
            if response and response.status_code in [200, 204]:
                time.sleep(1)
                success, message = self.boost_server(to_server_id)
                if success:
                    if from_server_id in self.boosted_servers:
                        del self.boosted_servers[from_server_id]
                    return True, f"Transferred boost from {from_server_id} to {to_server_id}"
        except Exception as e:
            return False, f"Transfer error: {str(e)[:50]}"
        
        return False, "Transfer failed"
    
    def auto_boost_servers(self, server_list):
        if not self.can_boost(server_list[0]):
            for boosted_id in list(self.boosted_servers.keys()):
                success, message = self.transfer_boost(boosted_id, server_list[0])
                if success:
                    return True, message
            return False, "No boosts available"
        
        for server_id in server_list:
            if self.can_boost(server_id):
                success, message = self.boost_server(server_id)
                if success:
                    return True, message
        
        return False, "Failed to boost any server"
    
    def start_rotation(self, server_list, interval_hours=24):
        if not server_list:
            return False, "No servers in rotation"
        
        self.server_rotation = server_list
        self.rotation_interval = interval_hours * 3600
        self.running = True
        
        self.boost_thread = threading.Thread(target=self._rotation_loop, daemon=True)
        self.boost_thread.start()
        
        return True, f"Started rotation with {len(server_list)} servers"
    
    def _rotation_loop(self):
        while self.running:
            self.check_boost_status()
            
            if self.available_boosts > 0:
                for server_id in self.server_rotation:
                    if self.can_boost(server_id):
                        self.boost_server(server_id)
                        break
            
            time.sleep(self.rotation_interval)
    
    def stop_rotation(self):
        self.running = False
        if self.boost_thread:
            self.boost_thread.join(timeout=2)
        return True, "Rotation stopped"
    
    def save_state(self):
        data = {
            "boosted_servers": self.boosted_servers,
            "available_boosts": self.available_boosts
        }
        with open("boost_state.json", "w") as f:
            json.dump(data, f, indent=2)
    
    def load_state(self):
        try:
            with open("boost_state.json", "r") as f:
                data = json.load(f)
                self.boosted_servers = data.get("boosted_servers", {})
                self.available_boosts = data.get("available_boosts", 2)
                return True
        except:
            return False