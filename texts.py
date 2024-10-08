class TextGenerator():
    def __init__(self):
        pass

    def get_welcome_text(self):
        return """
    Привет!

С этим ботом вы получите доступ к самым популярным нейросетям, таким как ChatGPT 4-o, DALL-E и Whisper.

Задавайте вопросы на любом языке, и бот быстро даст ответ.

Кстати, в день вы можете сделать до 5 запросов к GPT-4o-mini бесплатно.

Если захотите больше функций или нужна помощь, вот список команд:

/premium - Получить доступ к расширенному функционалу.
/account - Проверить информацию об аккаунте и подписке.
/model - Выбрать модель
/new_chat - Начать новый чат с нейросетью
/start - Посмотреть первоначальное меню
    """

    def get_premium_text(self):
        return """
    Тариф «Лайт» - хороший вариант, если вам нужен помощник для ежедневных задач: ответы на вопросы, решение тестов, описание картинок, распознавание фото и так далее. Безлимитный доступ к gpt-4o-mini, 25 запросов к gpt4-o и Dalle

Тариф «Смарт» — ваш выбор, когда вы каждый день взаимодействуете с нейросетями: создаете картинки, логотипы, пишете статьи и генерируете идеи. Безлимитный доступ к gpt-4o-mini, 50 запросов к gpt4-o и Dalle

Тариф «Про» — для тех, кто хочет максимум возможностей. Безлимитный доступ к gpt-4o-mini, 100 запросов к gpt4-o и Dalle
    """

    def get_account_text(self, user: dict):
        return """
    Подписка: {}
Дата истечения подписки: {}
Текущая модель: {}

Осталось запросов:
GPT-4o-mini: {}
GPT-4o: {}
DALL-E 3: {}
WHISPER: {}
    """.format(user.get("subscription"), user.get("subscription_expiry_date"), user.get("current_model"), user.get("gpt-4o-mini"), user.get("gpt-4o"), user.get("dall-e-3"), user.get("whisper"))