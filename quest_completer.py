import requests
import json
import time
import base64
import uuid

class QuestCompleter:
    def __init__(self, api_client):
        self.api = api_client
        
    def get_headers(self):
        headers = self.api.header_spoofer.get_headers()
        headers.update({
            "X-Discord-Locale": "en-US",
            "Referer": "https://discord.com/quest-home"
        })
        return headers
    
    def get_all_quests(self, raw=False):
        try:
            response = self.api.request("GET", "/quests/@me", headers=self.get_headers())
            if response and response.status_code == 200:
                data = response.json()
                if raw:
                    return data
                
                quests = []
                for quest in data.get("quests", []):
                    quest_info = {
                        "id": quest.get("id"),
                        "title": quest.get("config", {}).get("messages", {}).get("quest_name", "Unknown"),
                        "type": quest.get("config", {}).get("type", "unknown"),
                        "completed": quest.get("user_status", {}).get("completed_at") is not None,
                        "enrolled": quest.get("user_status", {}).get("enrolled_at") is not None
                    }
                    quests.append(quest_info)
                return quests
        except:
            pass
        return []
    
    def enroll_quest(self, quest_id):
        try:
            data = {"is_targeted": False, "location": 11}
            response = self.api.request("POST", f"/quests/{quest_id}/enroll", data=data, headers=self.get_headers())
            return response and response.status_code == 200
        except:
            return False
    
    def complete_quest(self, quest_id):
        try:
            data = {"timestamp": 60}
            response = self.api.request("POST", f"/quests/{quest_id}/video-progress", data=data, headers=self.get_headers())
            if response and response.status_code == 200:
                return True
            
            data = {"timestamp": 300, "application_id": quest_id}
            response = self.api.request("POST", f"/quests/{quest_id}/play-progress", data=data, headers=self.get_headers())
            return response and response.status_code == 200
        except:
            return False
    
    def auto_complete_all(self):
        quests = self.get_all_quests()
        results = []
        
        for quest in quests:
            quest_id = quest.get("id")
            if not quest.get("enrolled"):
                self.enroll_quest(quest_id)
                time.sleep(1)
            
            if not quest.get("completed"):
                success = self.complete_quest(quest_id)
                results.append({"quest_id": quest_id, "success": success})
                time.sleep(2)
        
        return results
    
    def test_api(self):
        try:
            response = self.api.request("GET", "/quests/@me", headers=self.get_headers())
            return response and response.status_code == 200
        except:
            return False
