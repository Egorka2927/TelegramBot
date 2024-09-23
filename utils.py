from telegram.ext import ContextTypes


def create_user_data(context: ContextTypes.DEFAULT_TYPE, user: dict):
    context.user_data["messages"] = []
    context.user_data["current_model"] = user.get("current_model")
    context.user_data["gpt-4o-mini"] = user.get("gpt-4o-mini")
    context.user_data["gpt-4o"] = user.get("gpt-4o")
    context.user_data["dall-e-3"] = user.get("dall-e-3")
    context.user_data["whisper"] = user.get("whisper")
    context.user_data["subscription"] = user.get("subscription", "Free")

def create_new_user(user_id):
    user = {
        "telegram_id": user_id,
        "current_model": "gpt-4o-mini",
        "gpt-4o-mini": 100,
        "gpt-4o": 100,
        "dall-e-3": 100,
        "whisper": 100,
        "subscription": "Free"
    }

    return user