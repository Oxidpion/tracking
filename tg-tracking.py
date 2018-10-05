import datetime as dt
import logging
from functools import wraps
from typing import Dict, List

import telegram.ext as tg
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import Session
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import run_async, Filters

import db
import messages as m
from db import initialize_table, User, find_user, get_all_task, RedmineTrackTask, find_task

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)


# Создает и закрывает сессию для обработчиков у телеграма
def create_session(f):
    @wraps(f)
    def wrapper(*args, **kwds):
        self = args[0]
        session = db.create_session(self.engine)

        kwds['session'] = session
        result = f(*args, **kwds)

        session.close()
        return result

    return wrapper


# Проверяет в БД на наличие пользователя и его настроек в redmine
# Inline не нужна проверка на пользователя и задачу, т.к. стадии задаются через inline кнопки, а пользователь не имеет к ним досттупа
# в этом случае надо предполагать что польователь и задача существует
# необходима проверка только на команде
def inline_restriction_rm_user(f):
    @wraps(f)
    def wrapper(*args, **kwds):
        self, bot, update = args
        session = kwds['session']

        user = find_user(session, update.callback_query.from_user.id)
        if user is None or user.redmine_user.empty():
            update.message.reply_text(m.HELP_MESSAGES)
            return

        return f(*args, **kwds)

    return wrapper


class Config:

    def __init__(self):
        self.token = '676578379:AAFQ4wcIQ_j6YjwLbiH2iFzxAqvoL8_ZP8M'

        self.redmine_host = 'https://redmine.url'

        self.proxy_url = 'socks5://78.46.102.189:5555'
        self.proxy_username = 'htc-proxy'
        self.proxy_password = 'Turbulentus@132'

        self.dsn_db = 'sqlite:///sqlite.db'


class RedmineSettingHandler:
    STAGE_SET_KEY = 1

    def __init__(self, engine: Engine, logger: logging.Logger) -> None:
        self.engine = engine
        self.logger = logger

    @run_async
    @create_session
    def start(self, bot: Bot, update: Update, session: Session):
        tg_user = update.message.from_user

        user = find_user(session, tg_user.id)
        if user is None:
            user = User(telegram_id=tg_user.id, telegram_name=tg_user.username)

        user.redmine_user.processed = False

        session.add(user)
        session.commit()

        update.message.reply_text(m.START_REDMINE_SETTINGS)
        update.message.reply_text(m.SET_REDMINE_KEY)

        return self.STAGE_SET_KEY

    @run_async
    @create_session
    def set_key(self, bot: Bot, update: Update, session: Session):
        tg_user = update.message.from_user

        user = find_user(session, tg_user.id)
        if user is None:
            update.message.reply_text(m.NOT_FOUND_USER)
            return tg.ConversationHandler.END

        user.redmine_user.key = update.message.text
        user.redmine_user.processed = True

        session.add(user.redmine_user)
        session.commit()

        update.message.reply_text(m.DONE_REDMINE_SETTINGS)
        update.message.reply_text(m.HELP_MESSAGES)

        return tg.ConversationHandler.END

    def create_tg_conversation_handler(self) -> tg.ConversationHandler:
        return tg.ConversationHandler(
            entry_points=[tg.CommandHandler('start', self.start)],
            states={
                self.STAGE_SET_KEY: [tg.MessageHandler(Filters.text, self.set_key)]
            },
            fallbacks=[]
        )


class RedmineTrackHandler:
    SET_TASK, SET_DATE, SET_WORKTIME, SAVE_TRACK, SET_COMMENT = range(10, 15)

    def __init__(self, engine: Engine, logger: logging.Logger) -> None:
        self.engine = engine
        self.logger = logger

    @run_async
    @create_session
    def start(self, bot: Bot, update: Update, session: Session):
        user = find_user(session, update.message.from_user.id)
        if user is None or user.redmine_user.empty():
            update.message.reply_text(m.NOT_FOUND_USER)
            return tg.ConversationHandler.END

        update.message.reply_text(m.WELCOME_TRACK_TASK)

        buttons = [InlineKeyboardButton(task.name, callback_data=str(task.id)) for task in get_all_task(session)]
        reply_markup = InlineKeyboardMarkup(build_menu(buttons, n_cols=2))
        update.message.reply_text(m.SET_TASK.format(self.track_task_to_str({})), reply_markup=reply_markup)

        return self.SET_TASK

    @run_async
    @create_session
    def task(self, bot: Bot, update: Update, user_data: Dict, session: Session):
        tg_message = update.callback_query.message

        user_data['task_id'] = update.callback_query.data
        user_data['task_name'] = find_task(session, user_data['task_id']).name

        reply_markup = InlineKeyboardMarkup(build_menu(self.get_inline_day_button, n_cols=3))
        bot.edit_message_text(m.SET_DATE.format(self.track_task_to_str(user_data)),
                              chat_id=tg_message.chat.id,
                              message_id=tg_message.message_id,
                              reply_markup=reply_markup)

        user_data['message_id'] = tg_message.message_id
        return self.SET_DATE

    @property
    def get_inline_day_button(self):
        buttons = [InlineKeyboardButton('Сегодня', callback_data='0'),
                   InlineKeyboardButton('Вчера', callback_data='-1')]
        for day_delta in range(2, 8):
            date = dt.date.today() - dt.timedelta(days=day_delta)
            date = '{}-{} ({})'.format(date.month, date.day, self.russian_weekday(date))
            buttons.append(InlineKeyboardButton(date, callback_data=str(-day_delta)))

        return buttons

    def russian_weekday(self, date: dt.date):
        return ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ', 'ВС'][date.weekday()]

    @run_async
    def date(self, bot: Bot, update: Update, user_data: Dict):
        tg_message = update.callback_query.message

        days = int(update.callback_query.data)
        user_data['date'] = dt.date.today() + dt.timedelta(days=days)

        buttons = build_menu(self.timedelta_buttons(0), n_cols=4)
        bot.edit_message_text(m.SET_WORKTIME.format(self.track_task_to_str(user_data)),
                              chat_id=tg_message.chat.id,
                              message_id=tg_message.message_id,
                              reply_markup=InlineKeyboardMarkup(buttons))
        return self.SET_WORKTIME

    def timedelta_buttons(self, current_time: float) -> List[InlineKeyboardButton]:
        buttons = list()
        for deltatime in [0.1, 0.5, 1, 2, 4, 8]:
            buttons.append(InlineKeyboardButton(str(deltatime), callback_data=str(deltatime)))
            if deltatime <= current_time:
                buttons.append(InlineKeyboardButton(str(-deltatime), callback_data=str(-deltatime)))
        return buttons

    @run_async
    def add_worktime(self, bot: Bot, update: Update, user_data: Dict):
        tg_message = update.callback_query.message

        user_data.setdefault('worktime', 0.0)
        user_data['worktime'] += float(update.callback_query.data)

        buttons = build_menu(self.timedelta_buttons(user_data['worktime']), n_cols=4,
                             footer_buttons=[InlineKeyboardButton('Дальше', callback_data='Next')])

        bot.edit_message_text(m.SET_WORKTIME.format(self.track_task_to_str(user_data)),
                              chat_id=tg_message.chat.id,
                              message_id=tg_message.message_id,
                              reply_markup=InlineKeyboardMarkup(buttons))
        return self.SET_WORKTIME

    @run_async
    def set_worktime(self, bot: Bot, update: Update, user_data: Dict):
        tg_message = update.callback_query.message

        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton('Готово', callback_data='Done')]])
        bot.edit_message_text(m.SET_COMMENT.format(self.track_task_to_str(user_data)),
                              chat_id=tg_message.chat.id,
                              message_id=tg_message.message_id,
                              reply_markup=reply_markup)
        return self.SET_COMMENT

    @run_async
    def comment(self, bot: Bot, update: Update, user_data: Dict):
        tg_message = update.message

        user_data['comment'] = tg_message.text

        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton('Готово', callback_data='Done')]])
        bot.edit_message_text(m.SET_COMMENT.format(self.track_task_to_str(user_data)),
                              chat_id=tg_message.chat.id,
                              message_id=user_data['message_id'],
                              reply_markup=reply_markup)

        return self.SET_COMMENT

    @run_async
    @create_session
    def done(self, bot: Bot, update: Update, user_data: Dict, session: Session):
        tg_message = update.callback_query.message

        track_task = RedmineTrackTask()
        track_task.user = find_user(session, update.callback_query.from_user.id)
        track_task.task = find_task(session, user_data['task_id'])
        track_task.date = user_data['date']
        track_task.worktime = user_data['worktime']
        track_task.comment = user_data.get('comment', 'Bot track time')

        session.add(track_task)
        session.commit()

        bot.edit_message_text(m.SAVE_TRACK_TIME.format(self.track_task_to_str(user_data)),
                              chat_id=tg_message.chat.id,
                              message_id=tg_message.message_id)
        user_data.clear()

        return tg.ConversationHandler.END

    @run_async
    def cancel(self, bot: Bot, update: Update, user_data: Dict):

        if 'message_id' in user_data:
            bot.delete_message(chat_id=update.message.chat.id, message_id=user_data['message_id'])
            user_data.clear()

        update.message.reply_text(m.TRACK_CANCEL)
        return tg.ConversationHandler.END

    def track_task_to_str(self, user_data: Dict):
        track = list()

        if 'task_name' in user_data:
            track.append('Задача - {}'.format(user_data['task_name']))

        if 'date' in user_data:
            date = user_data['date']
            track.append('Дата - {} ({})'.format(date, self.russian_weekday(date)))

        if 'worktime' in user_data:
            track.append('Часов - {}'.format(user_data['worktime']))

        if 'comment' in user_data:
            track.append('Комментарий - {}'.format(user_data['comment']))

        if len(track) == 0:
            track.append('Ничего')

        return '\n'.join(track).join(['\n', '\n'])

    def create_tg_conversation_handler(self) -> tg.ConversationHandler:
        return tg.ConversationHandler(
            entry_points=[tg.CommandHandler('track', self.start)],
            states={
                self.SET_TASK: [tg.CallbackQueryHandler(self.task, pattern='^\d+$', pass_user_data=True)],
                self.SET_DATE: [tg.CallbackQueryHandler(self.date, pattern='^[+-]?[\\d.]+$', pass_user_data=True)],
                self.SET_WORKTIME: [
                    tg.CallbackQueryHandler(self.add_worktime, pattern='^[+-]?[\\d.]+$', pass_user_data=True),
                    tg.CallbackQueryHandler(self.set_worktime, pattern='^Next$', pass_user_data=True)],
                self.SET_COMMENT: [tg.MessageHandler(Filters.text, self.comment, pass_user_data=True)],
            },
            fallbacks=[tg.CallbackQueryHandler(self.done, pattern='^Done$', pass_user_data=True),
                       tg.CommandHandler('cancel', self.cancel, pass_user_data=True)],
        )


class BotTracking:

    def __init__(self, config: Config, engine: Engine):
        self.updater = tg.Updater(config.token, workers=1, request_kwargs={
            'proxy_url': config.proxy_url,
            'urllib3_proxy_kwargs': {
                'username': config.proxy_username,
                'password': config.proxy_password,
            },
        })

        self.config = config
        self.engine = engine
        self.logger = logging.getLogger(__name__)

        dp = self.updater.dispatcher

        rm_setting_handler = RedmineSettingHandler(engine, self.logger).create_tg_conversation_handler()
        dp.add_handler(rm_setting_handler)

        rm_task_handler = RedmineTrackHandler(engine, self.logger).create_tg_conversation_handler()
        dp.add_handler(rm_task_handler)

        dp.add_error_handler(self.error)

    def error(self, bot, update, error):
        """Log Errors caused by Updates."""
        self.logger.warning('Update "%s" caused error "%s"', update, error)

    # Запускает бот
    def run(self):
        self.updater.start_polling()
        self.updater.idle()


def build_menu(buttons,
               n_cols,
               header_buttons=None,
               footer_buttons=None):
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)
    return menu


if __name__ == '__main__':
    config = Config()

    engine = create_engine(config.dsn_db, echo=True)
    initialize_table(engine)

    bot = BotTracking(config, engine)
    bot.run()
