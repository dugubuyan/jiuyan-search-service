"""公众号-券商映射模型"""
from typing import Optional
from pydantic import BaseModel


class BrokerAccountCreate(BaseModel):
    account_name: str
    broker_name: str


class BrokerAccountUpdate(BaseModel):
    account_name: Optional[str] = None
    broker_name: Optional[str] = None


class BrokerAccountItem(BaseModel):
    id: str
    account_name: str
    broker_name: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
