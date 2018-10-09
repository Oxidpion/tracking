import datetime as dt
import logging
from functools import wraps
from typing import Dict, List

import telegram.ext as tg
from redminelib import Redmine
from redminelib.exceptions import AuthError
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.orm import Session
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import run_async, Filters

import db
from config import Config
import messages as m
from db import initialize_table, User, find_user, TimeEntry
from utility import build_menu, russian_date, date_from_today

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG)

STAGE_SET_KEY, SET_ISSUE, SET_SPENT_ON, SET_HOURS, SAVE_ENTRY_TIME, SET_COMMENTS = range(
    6)


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
            update.message.reply_text(m.WELCOME_MESSAGES)
            return

        return f(*args, **kwds)

    return wrapper


class RedmineSettingHandler:
    """

    """

    def __init__(self, engine: Engine, config: Config,
                 logger: logging.Logger) -> None:
        self.engine = engine
        self.logger = logger
        self.config = config

    @run_async
    @create_session
    def start(self, bot: Bot, update: Update, session: Session):
        tg_user = update.message.from_user

        user = find_user(session, tg_user.id)
        if user is None:
            user = User(telegram_id=tg_user.id,
                        telegram_name=tg_user.first_name)  # add last_name if exists

        session.add(user)
        session.commit()

        update.message.reply_text(m.START_REDMINE_SETTINGS)
        update.message.reply_text(m.SET_REDMINE_KEY)

        return STAGE_SET_KEY

    @run_async
    @create_session
    def set_key(self, bot: Bot, update: Update, session: Session):
        tg_user = update.message.from_user

        user = find_user(session, tg_user.id)
        if user is None:
            update.message.reply_text(m.NOT_FOUND_USER)
            return tg.ConversationHandler.END

        try:
            redmine = Redmine(url=self.config.redmine_host,
                              key=update.message.text)
            redmine.auth()
        except AuthError:
            update.message.reply_text(m.INVALID_REDMINE_KEY)

            user.redmine_user.key = ''

            session.add(user.redmine_user)
            session.commit()
            return tg.ConversationHandler.END

        user.redmine_user.key = update.message.text

        session.add(user.redmine_user)
        session.commit()

        update.message.reply_text(m.DONE_REDMINE_SETTINGS)
        update.message.reply_text(m.WELCOME_MESSAGES)

        return tg.ConversationHandler.END

    def create_tg_conversation_handler(self) -> tg.ConversationHandler:
        return tg.ConversationHandler(
            entry_points=[tg.CommandHandler('start', self.start)],
            states={
                STAGE_SET_KEY: [tg.MessageHandler(Filters.text, self.set_key)]
            },
            fallbacks=[]
        )


class RedmineTrackHandler:

    def __init__(self, engine, config, logger) -> None:
        self.engine = engine
        self.config = config
        self.logger = logger

    @run_async
    @create_session
    def start(self, bot, update, user_data, session):
        user = find_user(session, update.message.from_user.id)
        if user is None or user.redmine_user.empty():
            update.message.reply_text(m.NOT_FOUND_USER)
            return tg.ConversationHandler.END

        update.message.reply_text(m.WELCOME_ENTRY_TIME)

        track_task = TimeEntry()
        track_task.user = user
        session.add(track_task)
        session.commit()
        user_data['track_task_id'] = track_task.id

        buttons = [InlineKeyboardButton(russian_date(d), callback_data=str(d))
                   for d in date_from_today(range(0, -8, -1))]
        message = update.message.reply_text(
            m.SET_SPENT_ON.format(self.track_task_to_str(user_data)),
            reply_markup=InlineKeyboardMarkup(build_menu(buttons, n_cols=2)))

        user_data['message_id'] = message.message_id

        return SET_SPENT_ON

    @run_async
    @create_session
    def spent_on(self, bot, update, user_data, session):
        tg_message = update.callback_query.message

        user_data['spent_on'] = dt.datetime.strptime(update.callback_query.data,
                                                     '%Y-%m-%d').date()

        user = find_user(session, update.effective_user.id)
        if user is None or user.redmine_user.empty():
            tg_message.reply_text(m.NOT_FOUND_USER)
            return tg.ConversationHandler.END

        redmine = Redmine(url=self.config.redmine_host,
                          key=user.redmine_user.key)

        issues = self.config.redmine_general_issue
        for issue in redmine.auth().issues:
            issues[issue.id] = issue.subject
        user_data['issues'] = issues

        buttons = [InlineKeyboardButton(name, callback_data=str(id)) for
                   id, name in issues.items()]
        reply_markup = InlineKeyboardMarkup(build_menu(buttons, n_cols=1))
        bot.edit_message_text(
            m.SET_ISSUE.format(self.track_task_to_str(user_data)),
            chat_id=tg_message.chat.id,
            message_id=tg_message.message_id,
            reply_markup=reply_markup)
        return SET_ISSUE

    @run_async
    def issue(self, bot, update, user_data):
        tg_message = update.callback_query.message

        issues = user_data.pop('issues')
        user_data['issue_id'] = int(update.callback_query.data)
        user_data['issue_name'] = issues[user_data['issue_id']]

        bot.edit_message_text(
            m.SET_COMMENTS.format(self.track_task_to_str(user_data)),
            chat_id=tg_message.chat.id,
            message_id=tg_message.message_id)
        return SET_COMMENTS

    @run_async
    def comment(self, bot, update, user_data):
        tg_message = update.message

        user_data['comment'] = tg_message.text

        bot.delete_message(chat_id=update.message.chat.id,
                           message_id=user_data['message_id'])

        buttons = build_menu(self.timedelta_buttons(), n_cols=4)
        message = update.message.reply_text(
            m.SET_HOURS.format(self.track_task_to_str(user_data)),
            reply_markup=InlineKeyboardMarkup(buttons))
        user_data['message_id'] = message.message_id

        return SET_HOURS

    def timedelta_buttons(self) -> List[InlineKeyboardButton]:
        buttons = [InlineKeyboardButton(delta, callback_data=delta) for delta in
                   ['0.1', '0.5', '1', '2', '4', '8']]
        buttons.append(InlineKeyboardButton('Сброс', callback_data='Reset'))
        return buttons

    @run_async
    def add_hours(self, bot, update, user_data):
        tg_message = update.callback_query.message

        user_data.setdefault('hours', 0.0)
        user_data['hours'] += float(update.callback_query.data)

        buttons = build_menu(self.timedelta_buttons(), n_cols=4,
                             footer_buttons=[InlineKeyboardButton('Готово',
                                                                  callback_data='Done')])
        bot.edit_message_text(
            m.SET_HOURS.format(self.track_task_to_str(user_data)),
            chat_id=tg_message.chat.id,
            message_id=tg_message.message_id,
            reply_markup=InlineKeyboardMarkup(buttons))
        return SET_HOURS

    @run_async
    def reset_hours(self, bot, update, user_data):
        tg_message = update.callback_query.message

        user_data['hours'] = 0

        buttons = build_menu(self.timedelta_buttons(), n_cols=4)
        bot.edit_message_text(
            m.SET_HOURS.format(self.track_task_to_str(user_data)),
            chat_id=tg_message.chat.id,
            message_id=tg_message.message_id,
            reply_markup=InlineKeyboardMarkup(buttons))
        return SET_HOURS

    @run_async
    @create_session
    def done(self, bot, update, user_data, session):

        if 'track_task_id' not in user_data:
            return tg.ConversationHandler.END

        entry_time = db.find_track(session, user_data['track_task_id'])
        if entry_time.saved is True:
            return tg.ConversationHandler.END

        tg_message = update.callback_query.message

        track_task = entry_time
        track_task.issue_id = user_data['issue_id']
        track_task.spent_on = user_data['spent_on']
        track_task.hours = user_data['hours']
        track_task.comments = user_data.get('comment', 'Default bot comments')
        track_task.saved = True

        redmine = Redmine(url=self.config.redmine_host,
                          key=track_task.user.redmine_user.key)
        redmine.time_entry.create(issue_id=track_task.issue_id,
                                  hours=track_task.hours,
                                  spent_on=track_task.spent_on,
                                  comments=track_task.comments)

        session.add(track_task)
        session.commit()

        bot.edit_message_text(
            m.SAVE_ENTRY_TIME.format(self.track_task_to_str(user_data)),
            chat_id=tg_message.chat.id,
            message_id=tg_message.message_id)
        user_data.clear()
        return tg.ConversationHandler.END

    @run_async
    @create_session
    def cancel(self, bot, update, user_data, session):

        if 'track_task_id' in user_data:
            track_task = db.find_track(session, user_data['track_task_id'])
            session.delete(track_task)
            session.commit()

        if 'message_id' in user_data:
            bot.delete_message(chat_id=update.message.chat.id,
                               message_id=user_data['message_id'])
            user_data.clear()

        update.message.reply_text(m.ENTRY_TIME_CANCEL)
        return tg.ConversationHandler.END

    def track_task_to_str(self, user_data):
        track = list()

        if 'issue_name' in user_data:
            track.append('Задача - {}'.format(user_data['issue_name']))

        if 'spent_on' in user_data:
            spent_on = user_data['spent_on']
            track.append('Дата - {}'.format(spent_on, russian_date(spent_on)))

        if 'hours' in user_data:
            track.append('Часов - {}'.format(user_data['hours']))

        if 'comment' in user_data:
            track.append('Комментарий - {}'.format(user_data['comment']))

        if len(track) == 0:
            track.append('Ничего')

        return '\n'.join(track).join(['\n', '\n'])

    def create_tg_conversation_handler(self):
        return tg.ConversationHandler(
            entry_points=[
                tg.CommandHandler('track', self.start, pass_user_data=True)],
            states={
                SET_SPENT_ON: [tg.CallbackQueryHandler(self.spent_on, pattern='^\d{4}-\d{2}-\d{2}$', pass_user_data=True)],
                SET_ISSUE: [tg.CallbackQueryHandler(self.issue, pattern='^\d+$', pass_user_data=True)],
                SET_COMMENTS: [tg.MessageHandler(Filters.text, self.comment, pass_user_data=True)],
                SET_HOURS: [
                    tg.CallbackQueryHandler(self.add_hours, pattern='^[\\d.]+$', pass_user_data=True),
                    tg.CallbackQueryHandler(self.reset_hours, pattern='^Reset$', pass_user_data=True)],
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

        rm_setting_handler = RedmineSettingHandler(engine, self.config,
                                                   self.logger).create_tg_conversation_handler()
        dp.add_handler(rm_setting_handler)

        rm_task_handler = RedmineTrackHandler(engine, self.config,
                                              self.logger).create_tg_conversation_handler()
        dp.add_handler(rm_task_handler)

        dp.add_handler(tg.CommandHandler('help', self.help))
        dp.add_error_handler(self.error)

    def error(self, bot: Bot, update: Update, error):
        """Log Errors caused by Updates."""
        self.logger.warning('Update "%s" caused error "%s"', update, error)

    def help(self, bot: Bot, update: Update):
        update.message.reply_text(m.HELP_MESSAGE)

    # Запускает бот
    def run(self):
        self.updater.start_polling()
        self.updater.idle()


if __name__ == '__main__':
    config = Config()

    engine = create_engine(config.dsn_db, echo=True)
    initialize_table(engine)

    bot = BotTracking(config, engine)
    bot.run()
