import telegram.ext as tg
import logging

from sqlalchemy.engine import Engine, create_engine
from telegram import Bot, Update
from telegram.ext import run_async

from db import initialize_table

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)


class Config:

    def __init__(self):
        self.token = '676578379:AAFQ4wcIQ_j6YjwLbiH2iFzxAqvoL8_ZP8M'

        self.redmine_host = 'https://redmine.url'
        self.redmine_username = 'user'
        self.redmine_password = 'password'

        self.proxy_url = 'socks5://78.46.102.189:5555'
        self.proxy_username = 'htc-proxy'
        self.proxy_password = 'Turbulentus@132'

        self.dsn_db = 'sqlite:///sqlite.db'


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
        self.logger = logging.getLogger(__name__)

        self.__bind_handler()

    # Связываеет названия команд с их обработчиками
    def __bind_handler(self):
        dp = self.updater.dispatcher
        dp.add_handler(tg.CommandHandler('start', self.start))
        dp.add_handler(tg.CommandHandler('track', self.track))
        # dp.add_error_handler()

    # Обработчик команды /start
    @run_async
    def start(self, bot: Bot, update: Update):
        self.logger.debug('Entering start')

        update.message.reply_text('Hi! \n Click this /track')

        self.logger.debug('Finishing start')

    # Обработчик команды /track
    @run_async
    def track(self, bot: Bot, update: Update):
        self.logger.debug('Entering track')

        update.message.reply_text('Not implement')

        self.logger.debug('Finishing track')

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
