import datetime
import enum
import secrets

from sqlalchemy import (BigInteger, Boolean, DateTime, Enum, ForeignKey, Numeric, String)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class EventStatus(str, enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"


class SplitType(str, enum.Enum):
    EQUAL = "equal"      # поровну между участниками траты
    CUSTOM = "custom"     # доли заданы вручную (реализуем на следующих этапах)


class Event(Base):
    """Мероприятие/событие, в рамках которого считаются траты."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    created_by: Mapped[int] = mapped_column(BigInteger)  # tg_user_id создателя
    chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[EventStatus] = mapped_column(Enum(EventStatus), default=EventStatus.ACTIVE)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    invite_token: Mapped[str] = mapped_column(String(32), unique=True, default=lambda: secrets.token_urlsafe(12))
    participants: Mapped[list["Participant"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    expenses: Mapped[list["Expense"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    editors: Mapped[list["EventEditor"]] = relationship(back_populates="event", cascade="all, delete-orphan")


class Participant(Base):
    """Участник события (может быть не привязан к Telegram-аккаунту)."""

    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    name: Mapped[str] = mapped_column(String(255))
    tg_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    event: Mapped["Event"] = relationship(back_populates="participants")

    paid_expenses: Mapped[list["Expense"]] = relationship(back_populates="payer")
    shares: Mapped[list["ExpenseShare"]] = relationship(back_populates="participant")


class Expense(Base):
    """Одна трата: кто платил, сколько, за что."""

    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    payer_id: Mapped[int] = mapped_column(ForeignKey("participants.id"))
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    split_type: Mapped[SplitType] = mapped_column(Enum(SplitType), default=SplitType.EQUAL)
    created_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=datetime.datetime.utcnow)

    event: Mapped["Event"] = relationship(back_populates="expenses")
    payer: Mapped["Participant"] = relationship(back_populates="paid_expenses")
    shares: Mapped[list["ExpenseShare"]] = relationship(back_populates="expense", cascade="all, delete-orphan")


class ExpenseShare(Base):
    """Связь траты с участниками, которые её потребляют (делят между собой)."""

    __tablename__ = "expense_shares"

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey("expenses.id"))
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"))
    share_amount: Mapped[float] = mapped_column(Numeric(12, 2))

    expense: Mapped["Expense"] = relationship(back_populates="shares")
    participant: Mapped["Participant"] = relationship(back_populates="shares")


class EventEditor(Base):
    """Пользователи Telegram, имеющие право редактировать событие (для совместного редактирования)."""

    __tablename__ = "event_editors"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    tg_user_id: Mapped[int] = mapped_column(BigInteger)
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    tg_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tg_first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    event: Mapped["Event"] = relationship(back_populates="editors")