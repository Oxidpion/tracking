from typing import List

from sqlalchemy import Column, Integer, String, Date, Float, ForeignKey, Text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker, Session

Base = declarative_base()


class User(Base):
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True)
    telegram_user = relationship('TelegramUser', uselist=False, back_populates='user')
    redmine_user = relationship('RedmineUser', uselist=False, back_populates='user')

    def __repr__(self) -> str:
        return 'User<id=%s>' % (self.id)

    def __init__(self, telegram_id: int, telegram_name: str, redmine_name: str = '',
                 redmine_password: str = '') -> None:
        self.telegram_user = TelegramUser(id=telegram_id, name=telegram_name)
        self.redmine_user = RedmineUser(name=redmine_name, key=redmine_password)


class TelegramUser(Base):
    __tablename__ = 'tg_user'
    id = Column(Integer, primary_key=True)
    name = Column(String(30), nullable=False)

    user_id = Column(Integer, ForeignKey('user.id'))
    user = relationship('User', back_populates='telegram_user')

    def __repr__(self) -> str:
        return 'TelegramUser<id=%s,name=%s>' % (self.id, self.name)

    def __init__(self, id: int, name: str) -> None:
        self.id = id
        self.name = name


class RedmineUser(Base):
    __tablename__ = 'rm_user'
    id = Column(Integer, primary_key=True)
    name = Column(String(30), nullable=False, default='')
    key = Column(String(30), nullable=False, default='')

    user_id = Column(Integer, ForeignKey('user.id'))
    user = relationship('User', back_populates='redmine_user')

    def __repr__(self) -> str:
        return 'RedmineUser<id=%s,name=%s>' % (self.id, self.name)

    def __init__(self, name: str, key: str) -> None:
        self.name = name
        self.key = key

    def empty(self):
        return self.name == '' and self.key == ''


class RedmineTrackTask(Base):
    __tablename__ = 'rm_track_task'
    id = Column(Integer, primary_key=True)
    date = Column(Date)
    worktime = Column(Float, nullable=False, default=0)
    comment = Column(Text)

    user_id = Column(Integer, ForeignKey('user.id'))
    user = relationship('User')

    task_id = Column(Integer, ForeignKey('rm_task.id'))
    task = relationship('RedmineTask')

    def __repr__(self) -> str:
        return 'RedmineTrackTask<txid=%s,user_id=%s,task_id=%s,date=%s,track_time=%s>' % (
            self.txid, self.user_id, self.task_id, self.date, self.worktime)


class RedmineTask(Base):
    __tablename__ = 'rm_task'
    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)

    def __repr__(self) -> str:
        return 'RedmineTask<id=%s,name=%s>' % (self.id, self.name)

    def __init__(self, name: str) -> None:
        self.name = name


def initialize_table(engine: Engine):
    create_tables = False
    for model in [TelegramUser, RedmineUser, User, RedmineTask, RedmineTrackTask]:
        if not engine.dialect.has_table(engine, model.__table__.name):
            model.__table__.create(bind=engine)
            create_tables = True

    if create_tables:
        session = create_session(engine)
        task1 = RedmineTask('Task 1')
        task2 = RedmineTask('Task 2')

        session.add_all((task1, task2))
        session.commit()
        session.close()


def create_session(engine: Engine) -> Session:
    Session = sessionmaker()
    Session.configure(bind=engine)
    return Session()


def find_user(session: Session, telegram_id: int):
    return session.query(User).join(TelegramUser).filter(TelegramUser.id == telegram_id).one_or_none()


def get_all_task(session: Session) -> List[RedmineTask]:
    return session.query(RedmineTask).all()


def find_task(session: Session, task_id: int) -> RedmineTask:
    return session.query(RedmineTask).filter(RedmineTask.id == task_id).one()


def find_track(session: Session, txid: int) -> RedmineTrackTask:
    return session.query(RedmineTrackTask).filter(RedmineTrackTask.txid == txid).one()
