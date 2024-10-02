from pymongo import MongoClient
from telegram.ext import BasePersistence, PersistenceInput
from dotenv import load_dotenv

load_dotenv()

class MongoDBPersistence(BasePersistence):

    def __init__(self, mongo_client: MongoClient):
        super().__init__(update_interval=600)
        self.mongo_client = mongo_client
        self.db = self.mongo_client.user_database
        self.users_collection = self.db.users

        store_data = {
            'user_data': True,
            'chat_data': False,
            'bot_data': False,
            'callback_data': False
        }
        
        self.store_data = PersistenceInput(**store_data)
    
    async def get_user_data(self):
        user_data = {}

        for user in self.users_collection.find():
            user_data[user["telegram_id"]] = {
                "current_model": user.get("current_model"),
                "gpt-4o-mini": user.get("gpt-4o-mini"),
                "gpt-4o": user.get("gpt-4o"),
                "dall-e-3": user.get("dall-e-3"),
                "whisper": user.get("whisper"),
                "subscription": user.get("subscription", "Free"),
                "last_free_request_date": user.get("last_free_request_date"),
                "subscription_expiry_date": user.get("subscription_expiry_date")
            }

        return user_data
    
    async def update_user_data(self, user_id, data: dict):
        if user_id:
            if "messages" in data.keys():
                data.pop("messages")
            
            if "chosen_premium" in data.keys():
                data.pop("chosen_premium")

            self.users_collection.update_one(              
                {"telegram_id": user_id},
                {"$set": data},
                upsert=True
            )
        else:
            self.users_collection.update_many(data)
    
    async def drop_user_data(self, user_id: int):
        self.users_collection.delete_one({"telegram_id": user_id})

    async def refresh_user_data(self, user_id: int, user_data: dict):
        pass

    async def get_chat_data(self):
        pass

    async def get_bot_data(self):
        pass

    async def update_chat_data(self):
        pass

    async def update_bot_data(self):
        pass

    async def update_conversation(self):
        pass

    async def get_conversations(self):
        pass

    async def drop_chat_data(self):
        pass

    async def flush(self):
        pass

    async def get_callback_data(self):
        pass

    async def refresh_bot_data(self):
        pass

    async def refresh_chat_data(self):
        pass

    async def update_callback_data(self):
        pass