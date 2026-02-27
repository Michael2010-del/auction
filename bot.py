import os
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from logic import *
import schedule
import threading
import time
from config import *
import cv2
import numpy as np
from math import sqrt, ceil, floor

bot = TeleBot(API_TOKEN)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_last_prize_id = None
_last_img = None

def gen_markup(id, is_re_auction=False):
    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    if is_re_auction:
        markup.add(InlineKeyboardButton("Получить за бонусы! 💰", callback_data=f"re_{id}"))
    else:
        markup.add(InlineKeyboardButton("Получить!", callback_data=str(id)))
    return markup

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.message.chat.id
    
    if call.data.startswith('re_'):
        prize_id = int(call.data.replace('re_', ''))
        
        active_auctions = manager.get_active_re_auctions()
        active_ids = [a[0] for a in active_auctions]
        
        if prize_id not in active_ids:
            bot.send_message(user_id, "Этот аукцион уже закончился!")
            return
        
        bonus_cost = None
        for auction in active_auctions:
            if auction[0] == prize_id:
                bonus_cost = auction[4]
                break
        
        user_bonus = manager.get_user_bonus(user_id)
        
        if user_bonus < bonus_cost:
            bot.send_message(user_id, f"❌ Недостаточно бонусов! Нужно: {bonus_cost}, у тебя: {user_bonus}")
            return
        
        if manager.get_winners_count(prize_id) < 1:
            if manager.spend_bonus(user_id, bonus_cost):
                res = manager.add_winner(user_id, prize_id)
                if res:
                    img = manager.get_prize_img(prize_id)
                    photo_path = os.path.join(BASE_DIR, 'img', img)
                    with open(photo_path, 'rb') as photo:
                        bot.send_photo(user_id, photo, 
                                     caption=f"🎉 Поздравляем! Ты получил картинку за {bonus_cost} бонусов!")
                else:
                    bot.send_message(user_id, 'Ты уже получил эту картинку!')
            else:
                bot.send_message(user_id, "Ошибка при списании бонусов")
        else:
            bot.send_message(user_id, "К сожалению, картинку уже кто-то получил!")
    
    else:
        prize_id = int(call.data) if call.data.isdigit() else call.data
        
        if manager.get_winners_count(prize_id) < int(manager.get_setting('winners_per_prize')):
            res = manager.add_winner(user_id, prize_id)
            if res:
                img = manager.get_prize_img(prize_id)
                photo_path = os.path.join(BASE_DIR, 'img', img)
                bonus = manager.get_setting('bonus_per_win')
                with open(photo_path, 'rb') as photo:
                    bot.send_photo(user_id, photo, 
                                 caption=f"Поздравляем! Ты получил картинку! +{bonus} бонусов! 💰")
            else:
                bot.send_message(user_id, 'Ты уже получил картинку!')
        else:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔄 Повторный аукцион за бонусы", 
                                          callback_data=f"re_auction_{prize_id}"))
            bot.send_message(user_id, 
                           "К сожалению, ты не успел получить картинку!\n"
                           "Хочешь попытаться ещё раз в повторном аукционе?", 
                           reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('re_auction_'))
def handle_re_auction_request(call):
    user_id = call.message.chat.id
    prize_id = int(call.data.replace('re_auction_', ''))
    
    if not manager.check_admin(user_id):
        bot.send_message(user_id, "Только администратор может создавать повторные аукционы!")
        return
    
    new_prize_id = manager.create_re_auction(prize_id)
    
    if new_prize_id:
        img = manager.get_prize_img(prize_id)
        bonus_cost = manager.get_setting('re_auction_bonus_cost')
        
        users = manager.get_users()
        for uid in users:
            with open(f'hidden_img/{img}', 'rb') as photo:
                bot.send_photo(uid, photo, 
                             caption=f"🔄 ПОВТОРНЫЙ АУКЦИОН!\n"
                                    f"Стоимость участия: {bonus_cost} бонусов 💰\n"
                                    f"Только один победитель!",
                             reply_markup=gen_markup(id=new_prize_id, is_re_auction=True))
        
        bot.send_message(user_id, "✅ Повторный аукцион создан и разослан всем пользователям!")
    else:
        bot.send_message(user_id, "❌ Не удалось создать повторный аукцион")

def send_message():
    global _last_prize_id, _last_img
    prize = manager.get_random_prize()
    if prize is None:
        manager.reset_used_prizes()
        prize = manager.get_random_prize()
        if prize is None:
            return
            
    prize_id, img = prize[:2]
    _last_prize_id, _last_img = prize_id, img
    manager.mark_prize_used(prize_id)
    hide_img(img)
    users = manager.get_users()
    for user in users:
        with open(f'hidden_img/{img}', 'rb') as photo:
            bot.send_photo(user, photo, 
                         caption="🎨 Новая картинка в аукционе!\n"
                                f"Трое первых получат её и +{manager.get_setting('bonus_per_win')} бонусов!",
                         reply_markup=gen_markup(id=prize_id))

def shedule_thread():
    time.sleep(5)
    send_message()
    
    interval = int(manager.get_setting('message_interval'))
    schedule.every(interval).minutes.do(send_message)
    
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

🎯 Правила:
• Три первых пользователя получат картинку
• За каждую полученную картинку начисляются бонусы 💰
• Бонусы можно потратить на повторных аукционах

Доступные команды:
/rating - рейтинг пользователей
/bonus - проверить свои бонусы
/get_my_score - моя коллекция
/re_auctions - активные повторные аукционы""")
        
        if _last_prize_id is not None and _last_img is not None:
            winners_count = manager.get_winners_count(_last_prize_id)
            if winners_count < int(manager.get_setting('winners_per_prize')):
                photo_path = os.path.join(BASE_DIR, 'hidden_img', _last_img)
                with open(photo_path, 'rb') as photo:
                    bot.send_photo(user_id, photo, 
                                 caption="🎨 Текущая картинка в аукционе!",
                                 reply_markup=gen_markup(id=_last_prize_id))

@bot.message_handler(commands=['bonus'])
def handle_bonus(message):
    user_id = message.chat.id
    bonus = manager.get_user_bonus(user_id)
    bot.send_message(user_id, f"💰 Твой бонусный счет: {bonus}")

@bot.message_handler(commands=['re_auctions'])
def handle_re_auctions(message):
    user_id = message.chat.id
    active = manager.get_active_re_auctions()
    
    if not active:
        bot.send_message(user_id, "Сейчас нет активных повторных аукционов!")
        return
    
    text = "🔄 Активные повторные аукционы:\n\n"
    for auction in active:
        prize_id, original_id, start, end, cost = auction
        text += f"🎨 Картинка #{prize_id}\n"
        text += f"💰 Стоимость: {cost} бонусов\n"
        text += f"⏰ Заканчивается: {end}\n\n"
    
    bot.send_message(user_id, text)

@bot.message_handler(commands=['rating'])
def handle_rating(message):
    res = manager.get_rating()
    w1, w2, w3 = 14, 10, 10
    sep = '| ' + '—' * w1 + ' | ' + '—' * w2 + ' | ' + '—' * w3 + ' |'
    lines = [
        f'| {"USER_NAME":<{w1}} | {"PRIZES":<{w2}} | {"BONUS":<{w3}} |',
        sep,
    ]
    for x in res:
        name = f'@{x[0]}' if x[0] else '(no name)'
        lines.append(f'| {name:<{w1}} | {x[1]:<{w2}} | {x[2]:<{w3}} |')
    bot.send_message(message.chat.id, '<pre>' + '\n'.join(lines) + '</pre>', parse_mode='HTML')

@bot.message_handler(commands=['get_my_score'])
def handle_get_my_score(message):
    user_id = message.chat.id
    
    won_prizes = manager.get_winners_img(user_id)
    all_images = os.listdir('img')
    
    image_paths = []
    for img in all_images:
        if img in won_prizes:
            image_paths.append(f'img/{img}')
        else:
            hidden_path = f'hidden_img/{img}'
            if not os.path.exists(hidden_path):
                hide_img(img)
            image_paths.append(hidden_path)
    
    collage = create_collage(image_paths)
    collage_path = f'temp_collage_{user_id}.jpg'
    cv2.imwrite(collage_path, collage)
    
    with open(collage_path, 'rb') as photo:
        bot.send_photo(user_id, photo, 
                     caption=f"🎨 Твоя коллекция!\n"
                            f"✅ Получено: {len(won_prizes)} из {len(all_images)}\n"
                            f"💰 Бонусы: {manager.get_user_bonus(user_id)}")
    
    os.remove(collage_path)

@bot.message_handler(commands=['admin'])
def handle_admin(message):
    user_id = message.chat.id
    if not manager.check_admin(user_id):
        bot.send_message(user_id, "У тебя нет прав администратора!")
        return
    
    text = """
🔐 Админ панель

Доступные команды:
/admin_add_prize - добавить новую картинку (отправь фото с подписью /admin_add_prize)
/admin_settings - настройки бота
/admin_prizes - список всех картинок
/admin_delete_prize [id] - удалить картинку
/admin_set_admin [user_id] - сделать пользователя админом
/admin_interval [минуты] - установить интервал рассылки
/admin_winners [количество] - установить количество победителей
/admin_bonus [количество] - установить бонус за победу
/admin_re_cost [бонусы] - установить стоимость повторного аукциона
/admin_re_duration [минуты] - установить длительность повторного аукциона
    """
    bot.send_message(user_id, text)

@bot.message_handler(commands=['admin_settings'])
def handle_admin_settings(message):
    user_id = message.chat.id
    if not manager.check_admin(user_id):
        return
    
    interval = manager.get_setting('message_interval')
    winners = manager.get_setting('winners_per_prize')
    bonus = manager.get_setting('bonus_per_win')
    re_cost = manager.get_setting('re_auction_bonus_cost')
    re_duration = manager.get_setting('re_auction_duration')
    
    text = f"""
⚙️ Текущие настройки:

🕐 Интервал рассылки: {interval} мин
👥 Победителей за раз: {winners}
💰 Бонус за победу: {bonus}
💎 Стоимость повторного аукциона: {re_cost}
⏱ Длительность повторного аукциона: {re_duration} мин
    """
    bot.send_message(user_id, text)

@bot.message_handler(commands=['admin_interval'])
def handle_admin_interval(message):
    user_id = message.chat.id
    if not manager.check_admin(user_id):
        return
    
    interval = message.text.split()[1]
    manager.update_setting('message_interval', interval)
    bot.send_message(user_id, f"✅ Интервал рассылки изменен на {interval} мин")

@bot.message_handler(commands=['admin_winners'])
def handle_admin_winners(message):
    user_id = message.chat.id
    if not manager.check_admin(user_id):
        return
    
    winners = message.text.split()[1]
    manager.update_setting('winners_per_prize', winners)
    bot.send_message(user_id, f"✅ Количество победителей изменено на {winners}")

@bot.message_handler(commands=['admin_bonus'])
def handle_admin_bonus(message):
    user_id = message.chat.id
    if not manager.check_admin(user_id):
        return
    
    bonus = message.text.split()[1]
    manager.update_setting('bonus_per_win', bonus)
    bot.send_message(user_id, f"✅ Бонус за победу изменен на {bonus}")

@bot.message_handler(commands=['admin_re_cost'])
def handle_admin_re_cost(message):
    user_id = message.chat.id
    if not manager.check_admin(user_id):
        return
    
    cost = message.text.split()[1]
    manager.update_setting('re_auction_bonus_cost', cost)
    bot.send_message(user_id, f"✅ Стоимость повторного аукциона изменена на {cost}")

@bot.message_handler(commands=['admin_re_duration'])
def handle_admin_re_duration(message):
    user_id = message.chat.id
    if not manager.check_admin(user_id):
        return
    
    duration = message.text.split()[1]
    manager.update_setting('re_auction_duration', duration)
    bot.send_message(user_id, f"✅ Длительность повторного аукциона изменена на {duration} мин")

@bot.message_handler(commands=['admin_add_prize'])
def handle_admin_add_prize(message):
    user_id = message.chat.id
    if not manager.check_admin(user_id):
        return
    
    bot.send_message(user_id, "Отправь мне фото, которое хочешь добавить в аукцион")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.chat.id
    if not manager.check_admin(user_id):
        return
    
    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    if not os.path.exists('img'):
        os.makedirs('img')
        
    file_name = f"prize_{int(time.time())}.jpg"
    file_path = os.path.join('img', file_name)
    
    with open(file_path, 'wb') as new_file:
        new_file.write(downloaded_file)
    
    manager.add_prize([(file_name,)], user_id)
    bot.send_message(user_id, f"✅ Картинка {file_name} успешно добавлена!")

@bot.message_handler(commands=['admin_prizes'])
def handle_admin_prizes(message):
    user_id = message.chat.id
    if not manager.check_admin(user_id):
        return
    
    prizes = manager.get_all_prizes()
    if not prizes:
        bot.send_message(user_id, "В базе нет картинок")
        return
    
    text = "📸 Список картинок:\n\n"
    for prize in prizes:
        prize_id, image, used, added_by, added_date = prize
        status = "✅ Использована" if used else "🔄 В очереди"
        text += f"ID: {prize_id}\nФайл: {image}\nСтатус: {status}\nДобавлено: {added_date}\n\n"
    
    bot.send_message(user_id, text)

@bot.message_handler(commands=['admin_delete_prize'])
def handle_admin_delete_prize(message):
    user_id = message.chat.id
    if not manager.check_admin(user_id):
        return
    
    prize_id = int(message.text.split()[1])
    manager.delete_prize(prize_id)
    bot.send_message(user_id, f"✅ Картинка с ID {prize_id} удалена")

@bot.message_handler(commands=['admin_set_admin'])
def handle_admin_set_admin(message):
    user_id = message.chat.id
    if not manager.check_admin(user_id):
        return
    
    new_admin_id = int(message.text.split()[1])
    manager.set_admin(new_admin_id)
    bot.send_message(user_id, f"✅ Пользователь {new_admin_id} теперь администратор")

def polling_thread():
    bot.polling(none_stop=True)

if __name__ == '__main__':
    manager = DatabaseManager(DATABASE)
    manager.create_tables()

    if not os.path.exists('img'):
        os.makedirs('img')
    if not os.path.exists('hidden_img'):
        os.makedirs('hidden_img')

    polling_thread = threading.Thread(target=polling_thread)
    polling_shedule = threading.Thread(target=shedule_thread)

    polling_thread.start()
    polling_shedule.start()