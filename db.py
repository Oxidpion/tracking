from typing import List

from sqlalchemy import Column, Integer, String, Date, Float, ForeignKey, Text, Boolean
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


class TimeEntry(Base):
    __tablename__ = 'time_entry'
    id = Column(Integer, primary_key=True)
    spent_on = Column(Date)
    hours = Column(Float, nullable=False, default=0)
    comments = Column(Text)
    saved = Column(Boolean, nullable=False, default=False)

    user_id = Column(Integer, ForeignKey('user.id'))
    user = relationship('User')

    issue_id = Column(Integer, ForeignKey('issue.id'))

    def __repr__(self) -> str:
        return 'TimeEntryБuser_id=%s,task_id=%s,date=%s,track_time=%s>' % (self.user_id, self.issue_id, self.spent_on, self.hours)


class Issue(Base):
    __tablename__ = 'issue'
    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)

    def __repr__(self) -> str:
        return 'Issue<id=%s,name=%s>' % (self.id, self.name)

    def __init__(self, name: str) -> None:
        self.name = name


def initialize_table(engine: Engine):
    create_tables = False
    for model in [TelegramUser, RedmineUser, User, Issue, TimeEntry]:
        if not engine.dialect.has_table(engine, model.__table__.name):
            model.__table__.create(bind=engine)
            create_tables = True

    if create_tables:
        session = create_session(engine)
        task1 = Issue('Task 1')
        task2 = Issue('Task 2')

        session.add_all((task1, task2))
        session.commit()
        session.close()


def create_session(engine: Engine) -> Session:
    Session = sessionmaker()
    Session.configure(bind=engine)
    return Session()


def find_user(session: Session, telegram_id: int):
    return session.query(User).join(TelegramUser).filter(TelegramUser.id == telegram_id).one_or_none()


def get_all_task(session: Session) -> List[Issue]:
    return session.query(Issue).all()


def find_track(session: Session, id: int) -> TimeEntry:
    return session.query(TimeEntry).filter(TimeEntry.id == id).one()

