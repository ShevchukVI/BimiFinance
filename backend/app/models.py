from sqlalchemy import Column, Date, Float, ForeignKey, Integer, String, BigInteger, Text
from sqlalchemy.orm import relationship
from app.database import Base

class Family(Base):
    __tablename__ = "families"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    invite_code = Column(String, unique=True, index=True, nullable=False)

    users = relationship("User", back_populates="family")
    categories = relationship("Category", back_populates="family")
    transactions = relationship("Transaction", back_populates="family")
    jars = relationship("Jar", back_populates="family")
    notes = relationship("Note", back_populates="family")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)
    tg_id = Column(BigInteger, unique=True, nullable=True, index=True)
    name = Column(String, nullable=False)
    mono_token = Column(String, nullable=True)  # ЗБЕРІГАЄ ШИФРОВАНИЙ Fernet-токен (НЕ plaintext!)
    role = Column(String, nullable=False, default="member")  # 'admin' | 'member'

    family = relationship("Family", back_populates="users")
    transactions = relationship("Transaction", back_populates="user")

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
    family = relationship("Family", back_populates="transactions")
    user = relationship("User", back_populates="transactions")
    category = relationship("Category", back_populates="transactions")

class Jar(Base):
    __tablename__ = "jars"
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)
    name = Column(String, nullable=False)
    balance = Column(Float, default=0.0)
    goal = Column(Float, nullable=False)
    family = relationship("Family", back_populates="jars")

class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True)
    family_id = Column(Integer, ForeignKey("families.id"), nullable=False)
    content = Column(Text, nullable=False)
    family = relationship("Family", back_populates="notes")