import os
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from logic import *
import schedule
import threading
import time
from config import *

bot = TeleBot(API_TOKEN)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# последняя разосланная картинка — чтобы отправить новым пользователям сразу после регистрации
_last_prize_id = None
_last_img = None

def gen_markup(id):
    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    markup.add(InlineKeyboardButton("Получить!", callback_data=str(id)))
    return markup

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    # callback_data от Telegram всегда строка
    prize_id = int(call.data) if call.data.isdigit() else call.data
    user_id = call.message.chat.id

    if manager.get_winners_count(prize_id) < 3:
        res = manager.add_winner(user_id, prize_id)
        if res:
            img = manager.get_prize_img(prize_id)
            photo_path = os.path.join(BASE_DIR, 'img', img)
            with open(photo_path, 'rb') as photo:
                bot.send_photo(user_id, photo, caption="Поздравляем! Ты получил картинку!")
        else:
            bot.send_message(user_id, 'Ты уже получил картинку!')
    else:
        bot.send_message(user_id, "К сожалению, ты не успел получить картинку! Попробуй в следующий раз!)")


def send_message():
    global _last_prize_id, _last_img
    try:
        prize = manager.get_random_prize()
        if prize is None:
            return  # все призы использованы или в базе нет призов
        prize_id, img = prize[:2]
        _last_prize_id, _last_img = prize_id, img
        manager.mark_prize_used(prize_id)
        hide_img(img)
        users = manager.get_users()
        for user in users:
            with open(f'hidden_img/{img}', 'rb') as photo:
                bot.send_photo(user, photo, reply_markup=gen_markup(id=prize_id))
    except Exception as e:
        print('send_message error:', e)

def shedule_thread():
    time.sleep(5)  # даём боту запуститься и подключиться
    send_message()  # первая картинка сразу после старта
    schedule.every().minute.do(send_message)
    while True:
        schedule.run_pending()
        time.sleep(1)

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.chat.id
    if user_id in manager.get_users():
        bot.reply_to(message, "Ты уже зарегестрирован!")
    else:
        manager.add_user(user_id, message.from_user.username)
        bot.reply_to(message, """Привет! Добро пожаловать! 
Тебя успешно зарегистрировали!
Каждый час тебе будут приходить новые картинки и у тебя будет шанс их получить!
Для этого нужно быстрее всех нажать на кнопку 'Получить!'

Только три первых пользователя получат картинку!)""")
        # Проверяем, есть ли текущая активная картинка, которую еще можно получить
        if _last_prize_id is not None and _last_img is not None:
            winners_count = manager.get_winners_count(_last_prize_id)
            if winners_count < 3:
                # Картинка еще доступна - отправляем с кнопкой
                try:
                    photo_path = os.path.join(BASE_DIR, 'hidden_img', _last_img)
                    with open(photo_path, 'rb') as photo:
                        bot.send_photo(user_id, photo, reply_markup=gen_markup(id=_last_prize_id))
                except FileNotFoundError:
                    pass
            else:
                # Картинки уже раздали на аукционе
                bot.send_message(user_id, "Картинки уже раздали на аукционе! Жди следующую рассылку!")

@bot.message_handler(commands=['rating'])
def handle_rating(message):
    res = manager.get_rating()
    w1, w2 = 14, 12
    sep = '| ' + '—' * w1 + ' | ' + '—' * w2 + ' |'
    lines = [
        f'| {"USER_NAME":<{w1}} | {"COUNT_PRIZE":<{w2}} |',
        sep,
    ]
    for x in res:
        name = f'@{x[0]}' if x[0] else '(no name)'
        lines.append(f'| {name:<{w1}} | {x[1]:<{w2}} |')
    bot.send_message(message.chat.id, '<pre>' + '\n'.join(lines) + '</pre>', parse_mode='HTML')


def polling_thread():
    bot.polling(none_stop=True)

if __name__ == '__main__':
    manager = DatabaseManager(DATABASE)
    manager.create_tables()

    polling_thread = threading.Thread(target=polling_thread)
    polling_shedule  = threading.Thread(target=shedule_thread)

    polling_thread.start()
    polling_shedule.start()