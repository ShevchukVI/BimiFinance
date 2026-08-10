from sqlalchemy import Column, Date, Float, ForeignKey, Integer, String, BigInteger, Text
from sqlalchemy.orm import relationship
from app.database import Base


class Family(Base):
    __tablename__ = "families"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    invite_code = Column(String, unique=True, index=True, nullable=False)

    memberships = relationship("FamilyMember", back_populates="family", cascade="all, delete-orphan")
    users = relationship("User", secondary="family_members", back_populates="families", viewonly=True)
    categories = relationship("Category", back_populates="family")
    transactions = relationship("Transaction", back_populates="family")
    jars = relationship("Jar", back_populates="family")
    notes = relationship("Note", back_populates="family")


class FamilyMember(Base):
    __tablename__ = "family_members"
    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), primary_key=True)
    role = Column(String, nullable=False, default="member")

    user = relationship("User", back_populates="memberships", overlaps="families,memberships,user")
    family = relationship("Family", back_populates="memberships", overlaps="families,memberships,family")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, unique=True, nullable=True, index=True)
    name = Column(String, nullable=False)
    mono_token = Column(String, nullable=True)
    current_active_family_id = Column(Integer, ForeignKey("families.id"), nullable=True)

    memberships = relationship("FamilyMember", back_populates="user", cascade="all, delete-orphan")
    families = relationship("Family", secondary="family_members", back_populates="users", viewonly=True, overlaps="families,memberships")
    transactions = relationship("Transaction", back_populates="user")
    bank_accounts = relationship("BankAccount", back_populates="user", cascade="all, delete-orphan")


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)
    icon = Column(String, nullable=False)
    name = Column(String, nullable=False)
    color = Column(String, nullable=False)
    type = Column(String, nullable=False)
    family = relationship("Family", back_populates="categories")
    transactions = relationship("Transaction", back_populates="category")


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    category_id = Column(Integer, ForeignKey("categories.id"))
    amount = Column(Float, nullable=False)
    type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    note = Column(String, default="")
    account = Column(String, nullable=False)
    mono_id = Column(String, unique=True, nullable=True, index=True)
    date = Column(Date, nullable=False)
    currency = Column(String, default="UAH", nullable=False)  # UAH/USD/EUR...
    jar_id = Column(Integer, ForeignKey("jars.id"), nullable=True)  # deposit/withdrawal to/from jar
    family = relationship("Family", back_populates="transactions")
    user = relationship("User", back_populates="transactions")
    category = relationship("Category", back_populates="transactions")
    jar = relationship("Jar", back_populates="transactions")


class Jar(Base):
    __tablename__ = "jars"
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)
    name = Column(String, nullable=False)
    # balance — зберігаємо фізично для зворотної сумісності, але НЕ використовуємо
    # для розрахунків. Баланс скарбнички тепер ДИНАМІЧНИЙ:
    #   SUM(amount) транзакцій з jar_id = this.id (поповнення +, зняття -).
    balance = Column(Float, default=0.0)
    goal = Column(Float, nullable=False)
    currency = Column(String, default="UAH", nullable=False)
    family = relationship("Family", back_populates="jars")
    transactions = relationship("Transaction", back_populates="jar")


class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)
    content = Column(Text, nullable=False)
    family = relationship("Family", back_populates="notes")


class BankAccount(Base):
    __tablename__ = "bank_accounts"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    provider = Column(String, nullable=False, default="monobank")
    external_account_id = Column(String, nullable=False)
    name = Column(String, nullable=True)

    user = relationship("User", back_populates="bank_accounts")


class UtilityMeter(Base):
    __tablename__ = "utility_meters"
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)
    name = Column(String, nullable=False)
    utility_type = Column(String, nullable=False)  # electricity, gas, water, heating
    unit = Column(String, nullable=False)  # kWh, m³, etc.
    tariff = Column(Float, default=0.0)  # current tariff per unit

    family = relationship("Family")
    readings = relationship("UtilityReading", back_populates="meter", cascade="all, delete-orphan")


class UtilityReading(Base):
    __tablename__ = "utility_readings"
    id = Column(Integer, primary_key=True)
    meter_id = Column(Integer, ForeignKey("utility_meters.id"), nullable=False)
    date = Column(Date, nullable=False)
    value = Column(Float, nullable=False)
    amount_paid = Column(Float, default=0.0)
    note = Column(String, default="")

    meter = relationship("UtilityMeter", back_populates="readings")
