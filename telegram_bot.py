import os
import logging
import utils
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.constants import ParseMode
from telegram.ext import filters, MessageHandler, ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, PreCheckoutQueryHandler
from openai import OpenAI, BadRequestError
from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient
from texts import TextGenerator
from mongodb_persistence import MongoDBPersistence
from datetime import datetime

class TelegramBot():
    def __init__(self):
        load_dotenv()

        print("Connecting to the database...")

        self.mongo_client = MongoClient(os.environ.get("MONGO_DB_URI"))

        self.check_database_connection()

        self.openai_client = OpenAI(
            organization=os.environ.get("ORGANIZATION_ID"),
            api_key=os.environ.get("OPENAI_API_KEY")
        )

        self.initialize_logging()

        self.persistence = MongoDBPersistence(self.mongo_client)

        self.application = ApplicationBuilder().token(os.environ.get("TELEGRAM_BOT_API_KEY")).persistence(self.persistence).build()

        self.add_handlers()

        self.text_generator = TextGenerator()
    
    def check_database_connection(self):
        try:
            self.mongo_client.admin.command('ping')
            print("Connection established!")
        except Exception as ex:
            print(ex)
    
    def initialize_logging(self):
        logging.basicConfig(
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            level=logging.INFO
        )
    
    def check_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if len(context.user_data) == 0:
            db = self.mongo_client.user_database

            user_id = update.effective_user.id

            user = db.users.find_one({"telegram_id": user_id})

            if user == None:
                user = utils.create_new_user(user_id)

                db.users.insert_one(user)

            utils.create_user_data(context, user)
        
        if "messages" not in context.user_data:
            context.user_data["messages"] = []
        
        if context.user_data["subscription"] != "Free":
            if datetime.fromisoformat(context.user_data["subscription_expiry_date"]) <= datetime.now():
                context.user_data["subscription"] = "Free"
                context.user_data["last_free_request_date"] = datetime.now().date().isoformat()
                context.user_data["subscription_expiry_date"] = "Безлимит"
                context.user_data["gpt-4o-mini"] = 5
                context.user_data["gpt-4o"] = 0
                context.user_data["dall-e-3"] = 0
                context.user_data["whisper"] = 0

            return
        
        current_date = datetime.now().date().isoformat()

        if context.user_data["last_free_request_date"] != current_date:
            context.user_data["last_free_request_date"] = current_date
            context.user_data["gpt-4o-mini"] = 5

    async def info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.check_data(update, context)

        message = self.text_generator.get_info_text()

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=message
        )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.check_data(update, context)

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=self.text_generator.get_welcome_text()
        )

    async def start_new_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.check_data(update, context)

        context.user_data["messages"] = []

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Новый чат создан. Пишите запросы"
        )
    
    async def check_message_type(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.message.text

        if len(update.message.photo) > 0:
            caption = update.message.caption

            if not caption:
                caption = ""

            file_id = update.message.photo[-1].file_id

            new_file = await context.bot.get_file(file_id)

            url = new_file.file_path

            message = [
                {"type": "text", "text": caption},
                {
                "type": "image_url",
                "image_url": {"url": url},
                },
            ]
        elif update.message.voice:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Эта модель не распознает голосовые сообщения"
            )

            message = None

        return message
        
    async def handle_chat_model_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            message = await self.check_message_type(update, context)

            if not message:
                return

            user_id = update.effective_user.id

            context.user_data["messages"].append({"role": "user", "content": message})

            completion = self.openai_client.chat.completions.create(
                model=context.user_data["current_model"],
                messages=context.user_data["messages"],
            )

            response = completion.choices[0].message.content

            if len(response) > 4096:
                with open("response{}.txt".format(user_id), "w", encoding="utf-8", errors='ignore') as file:
                    file.write(response)
            
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=open("response{}.txt".format(user_id), "r", encoding="utf-8", errors="ignore"),
                    caption="Ответ слишком длинный, поэтому записал его в текстовый файл"
                )

                os.remove("response{}.txt".format(user_id))
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=response,
                    parse_mode=ParseMode.MARKDOWN
                )

            context.user_data["messages"].append({"role": "system", "content": response})
        except Exception as ex:
            print(ex)

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Что то пошло не так, попробуйте снова. Убедитесь, что вы присылаете текст и/или фотографию не файлом."
            )
    
    async def handle_image_model_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            message = update.message.text

            generated_image_data = self.openai_client.images.generate(
                model=context.user_data["current_model"],
                prompt=message,
                n=1,
                size="1024x1024",
                quality="standard"
            )

            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=generated_image_data.data[0].url
            )
        except BadRequestError as ex:
            if ex.code == "content_policy_violation":
                print(ex)
                
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="Ваш запрос содержит текст, недопустимый системой безопасности openAi"
                )
            else:
                print(ex)

                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="Эта модель распознает только текст"
                )
        except Exception as ex:
            print(ex)

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Эта модель распознает только текст"
            )
    
    async def handle_voice_model_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try: 
            file_id = update.message.voice.file_id

            new_file = await context.bot.get_file(file_id)

            random_id = uuid.uuid4()

            file_name = str(random_id) + "-" + str(update.effective_user.id) + ".mp3"

            await new_file.download_to_drive("voice_messages/" + file_name)

            with open("voice_messages/" + file_name, "rb") as audio_file:
                transcript = self.openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=transcript.text
            )

            os.remove("voice_messages/" + file_name)
        except Exception as ex:
            print(ex)

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Эта модель принимает только голосовые сообщения"
            )

    async def chat_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.check_data(update, context)

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Обрабатываю запрос..."
        )

        current_model = context.user_data["current_model"]

        if context.user_data[current_model] != "Безлимит":

            if context.user_data[current_model] <= 0:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="У вас больше нет запросов на эту модель"
                )

                return
            
            context.user_data[current_model] -= 1

        chat_models = ["gpt-4o-mini", "gpt-4o"]

        if current_model in chat_models:
            await self.handle_chat_model_request(update, context)
        elif current_model == "dall-e-3":
            await self.handle_image_model_request(update, context)
        else:
            await self.handle_voice_model_request(update, context)

    async def choose_premium(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.check_data(update, context)

        keyboard = [
            [InlineKeyboardButton("Лайт 499 руб.", callback_data="Lite")],
            [InlineKeyboardButton("Смарт 999 руб.", callback_data="Smart")],
            [InlineKeyboardButton("Про 1499 руб.", callback_data="Pro")],
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=self.text_generator.get_premium_text(),
            reply_markup=reply_markup
        )
    
    async def handle_choose_premium_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.check_data(update, context)
        
        query = update.callback_query

        await query.answer()

        chosen_premium = query.data

        amount = None

        if chosen_premium == "Lite":
            amount = 499 * 100
        elif chosen_premium == "Smart":
            amount = 999 * 100
        else:
            amount = 1499 * 100

        await query.delete_message()

        pay_button = InlineKeyboardButton("Оплатить {} руб.".format(int(amount / 100)), pay=True)
        go_back_button = InlineKeyboardButton("Назад", callback_data="back_to_premium")

        keyboard = [[pay_button], [go_back_button]]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_invoice(
            chat_id=update.effective_chat.id,
            title="Подписка на бота",
            description="Активация подписки на бота на 30 дней",
            payload="Bot-Subscription-{}".format(chosen_premium),
            provider_token=os.environ.get("PROVIDER_TOKEN"),
            currency="RUB",
            prices=[LabeledPrice(label="Подписка на 1 месяц", amount=amount)],
            reply_markup=reply_markup,
            need_email=True,
            send_email_to_provider=True,
            provider_data={
                "receipt": {
                    "items": [
                        {
                            "description": "Подписка на бота {}".format(chosen_premium),
                            "quantity": "1.00",
                            "amount": {
                                "value": str(amount / 100),
                                "currency": "RUB"
                            },
                            "vat_code": 1
                        }
                    ]
                }
            }
        )
    
    async def answer_pre_checkout_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.pre_checkout_query

        invoice_payloads = ["Bot-Subscription-Lite", "Bot-Subscription-Smart", "Bot-Subscription-Pro"]

        if query.invoice_payload not in invoice_payloads:
            await query.answer(ok=False, error_message="Something went wrong")
        else:
            context.user_data["chosen_premium"] = query.invoice_payload.split("-")[2]
            await query.answer(ok=True)
    
    async def successful_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.user_data["chosen_premium"] == "Lite":
            context.user_data["gpt-4o-mini"] = "Безлимит"
            context.user_data["gpt-4o"] = 25
            context.user_data["dall-e-3"] = 25
            context.user_data["whisper"] = "Безлимит"
            context.user_data["subscription"] = "Lite"
        elif context.user_data["chosen_premium"] == "Smart":
            context.user_data["gpt-4o-mini"] = "Безлимит"
            context.user_data["gpt-4o"] = 50
            context.user_data["dall-e-3"] = 50
            context.user_data["whisper"] = "Безлимит"
            context.user_data["subscription"] = "Smart"
        else:
            context.user_data["gpt-4o-mini"] = "Безлимит"
            context.user_data["gpt-4o"] = 100
            context.user_data["dall-e-3"] = 50
            context.user_data["whisper"] = "Безлимит"
            context.user_data["subscription"] = "Pro"
        
        current_date_list = datetime.now().date().isoformat().split("-")

        if current_date_list[1] == "12":
            context.user_data["subscription_expiry_date"] = str(int(current_date_list[0]) + 1) + "-01-" + current_date_list[2]
        else:
            month = str(int(current_date_list[1]) + 1)

            if len(month) == 1:
                month = "0" + month

            context.user_data["subscription_expiry_date"] = current_date_list[0] + "-" + month + "-" + current_date_list[2]

        context.user_data.pop("chosen_premium")

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Оплата прошла успешно!"
        )

    async def handle_go_back_to_premium(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.check_data(update, context)

        query = update.callback_query

        await query.answer()

        keyboard = [
            [InlineKeyboardButton("Лайт 499 руб.", callback_data="Lite")],
            [InlineKeyboardButton("Смарт 999 руб.", callback_data="Smart")],
            [InlineKeyboardButton("Про 1499 руб.", callback_data="Pro")],
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.delete_message()

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=self.text_generator.get_premium_text(),
            reply_markup=reply_markup
        )

    async def view_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.check_data(update, context)

        text = self.text_generator.get_account_text(context.user_data)
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text
        )

    async def choose_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.check_data(update, context)

        keyboard = [
            [InlineKeyboardButton("gpt-4o-mini", callback_data="gpt-4o-mini")],
            [InlineKeyboardButton("gpt-4o", callback_data="gpt-4o")],
            [InlineKeyboardButton("dall-e-3", callback_data="dall-e-3")],
            [InlineKeyboardButton("whisper", callback_data="whisper")]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Выберите модель:",
            reply_markup=reply_markup
        )

    async def handle_choose_model_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.check_data(update, context)

        query = update.callback_query

        await query.answer()

        chosen_model = query.data

        context.user_data["current_model"] = chosen_model

        await query.edit_message_text(
            text="Вы выбрали модель: {}. Можете отправлять запрос".format(chosen_model)
        )

        await self.start_new_chat(update, context)
    
    def add_handlers(self):
        start_handler = CommandHandler("start", self.start)
        new_chat_handler = CommandHandler("new_chat", self.start_new_chat)
        info_handler = CommandHandler("info", self.info)
        premium_handler = CommandHandler("premium", self.choose_premium)
        account_handler = CommandHandler("account", self.view_account)
        message_handler = MessageHandler((filters.TEXT & (~filters.COMMAND)) | filters.PHOTO | filters.VOICE, self.chat_request)
        choose_model_handler = CommandHandler("model", self.choose_model)
        choose_model_button_handler = CallbackQueryHandler(self.handle_choose_model_button, pattern="^(gpt|dall-e|whisper)")
        choose_premium_button_handler = CallbackQueryHandler(self.handle_choose_premium_button, pattern="Lite|Smart|Pro")
        go_back_to_premium_handler = CallbackQueryHandler(self.handle_go_back_to_premium, pattern="back_to_premium")
        pre_checkout_query_handler = PreCheckoutQueryHandler(self.answer_pre_checkout_query)
        successful_payment_handler = MessageHandler(filters.SUCCESSFUL_PAYMENT, self.successful_payment)

        self.application.add_handler(start_handler)
        self.application.add_handler(message_handler)
        self.application.add_handler(new_chat_handler)
        self.application.add_handler(info_handler)
        self.application.add_handler(premium_handler)
        self.application.add_handler(account_handler)
        self.application.add_handler(choose_model_handler)
        self.application.add_handler(choose_model_button_handler)
        self.application.add_handler(choose_premium_button_handler)
        self.application.add_handler(go_back_to_premium_handler)
        self.application.add_handler(pre_checkout_query_handler)
        self.application.add_handler(successful_payment_handler)
    
    def run(self):
        self.application.run_polling()

if __name__ == "__main__":
    telegram_bot = TelegramBot()
    telegram_bot.run()