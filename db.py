from sqlalchemy import Column, Integer, String, Date, Float, ForeignKey, Text, Boolean
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Session, sessionmaker

Base = declarative_base()


class User(Base):
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True)

    telegram_user_id = Column(Integer, ForeignKey('tg_user.id'))
    telegram_user = relationship('TelegramUser')

    redmine_user_id = Column(Integer, ForeignKey('rm_user.id'))
    redmine_user = relationship('RedmineUser')

    def __repr__(self) -> str:
        return 'User<id=%s>' % (self.id)


class TelegramUser(Base):
    __tablename__ = 'tg_user'
    id = Column(Integer, primary_key=True)
    name = Column(String(30), nullable=False)

    def __repr__(self) -> str:
        return 'TelegramUser<id=%s,name=%s>' % (self.id, self.name)


class RedmineUser(Base):
    __tablename__ = 'rm_user'
    id = Column(Integer, primary_key=True)
    name = Column(String(30), nullable=False)
    password = Column(String(30), nullable=False)

    def __repr__(self) -> str:
        return 'RedmineUser<id=%s,name=%s>' % (self.id, self.name)


class RedmineTrackTask(Base):
    __tablename__ = 'rm_track_task'
    id = Column(Integer, primary_key=True)
    date = Column(Date)
    track_time = Column(Float, nullable=False, default=0)
    comment = Column(Text)
    processed = Column(Boolean, nullable=False, default=False)

    user_id = Column(Integer, ForeignKey('user.id'))
    user = relationship('User')

    task_id = Column(Integer, ForeignKey('rm_task.id'))
    task = relationship('RedmineTask')

    def __repr__(self) -> str:
        return 'RedmineTrackTask<user_id=%s,task_id=%s,date=%s,track_time=%s>' % (
            self.user_id, self.task_id, self.date, self.track_time)


class RedmineTask(Base):
    __tablename__ = 'rm_task'
    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)

    def __repr__(self) -> str:
        return 'RedmineTask<id=%s,name=%s>' % (self.id, self.name)


def initialize_table(engine: Engine):
    for model in [TelegramUser, RedmineUser, User, RedmineTask, RedmineTrackTask]:
        if not engine.dialect.has_table(engine, model.__table__.name):
            model.__table__.create(bind=engine)


def create_session(engine: Engine) -> Session:
    Session = sessionmaker()
    Session.configure(bind=engine)
    return Session()
