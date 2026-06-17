from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ConsoleUser(Base):
    __tablename__ = "console_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    first_name: Mapped[str] = mapped_column(String(64), default="")
    last_name: Mapped[str] = mapped_column(String(64), default="")
    email: Mapped[str] = mapped_column(String(256), default="")
    password_hash: Mapped[str] = mapped_column(Text)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class AzureConnection(Base):
    __tablename__ = "azure_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64))
    client_id: Mapped[str] = mapped_column(String(256))
    client_secret_encrypted: Mapped[str] = mapped_column(Text)
    auth_type: Mapped[str] = mapped_column(String(16), default="oauth")
    subscription_id: Mapped[str] = mapped_column(String(64))
    subscription_name: Mapped[str] = mapped_column(String(256), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AzureAuthSession(Base):
    __tablename__ = "azure_auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    flow_type: Mapped[str] = mapped_column(String(16))
    flow_data_encrypted: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    tenant_id: Mapped[str] = mapped_column(String(64), default="")
    tenant_name: Mapped[str] = mapped_column(String(256), default="")
    username: Mapped[str] = mapped_column(String(256), default="")
    refresh_token_encrypted: Mapped[str] = mapped_column(Text, default="")
    oauth_client_id: Mapped[str] = mapped_column(String(64), default="")
    subscriptions_json: Mapped[str] = mapped_column(Text, default="[]")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class Workshop(Base):
    __tablename__ = "workshops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True)
    resource_group: Mapped[str] = mapped_column(String(128))
    location: Mapped[str] = mapped_column(String(64))
    subscription_id: Mapped[str] = mapped_column(String(64))
    vm_count: Mapped[int] = mapped_column(Integer, default=0)
    schedule_start_hour: Mapped[int] = mapped_column(Integer, default=7)
    schedule_stop_hour: Mapped[int] = mapped_column(Integer, default=19)
    schedule_timezone: Mapped[str] = mapped_column(String(64), default="Europe/Paris")
    schedule_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    duration_days: Mapped[int] = mapped_column(Integer, default=5)
    status: Mapped[str] = mapped_column(String(32), default="creating")
    estimated_monthly_cost_eur: Mapped[float] = mapped_column(Float, default=0.0)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("console_users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class VirtualMachine(Base):
    __tablename__ = "virtual_machines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workshop_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(128))
    os_type: Mapped[str] = mapped_column(String(64))
    vm_size: Mapped[str] = mapped_column(String(64))
    admin_username: Mapped[str] = mapped_column(String(64))
    admin_password_encrypted: Mapped[str] = mapped_column(Text)
    public_ip: Mapped[str] = mapped_column(String(64), default="")
    private_ip: Mapped[str] = mapped_column(String(64), default="")
    remote_protocol: Mapped[str] = mapped_column(String(16), default="")
    remote_port: Mapped[int] = mapped_column(Integer, default=0)
    power_state: Mapped[str] = mapped_column(String(32), default="unknown")
    azure_vm_id: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(32), default="creating")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
