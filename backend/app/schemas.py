from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ConsoleLoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=6)


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    first_name: str = Field(min_length=1, max_length=64)
    last_name: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=3, max_length=256)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Le nom d'utilisateur ne peut contenir que des lettres, chiffres, tirets et underscores")
        return cleaned


class UserUpdateRequest(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=64)
    last_name: Optional[str] = Field(None, min_length=1, max_length=64)
    email: Optional[str] = Field(None, min_length=3, max_length=256)
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None


class AdminSetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=6)
    must_change_password: bool = False


class UserResponse(BaseModel):
    id: int
    username: str
    first_name: str
    last_name: str
    email: str
    display_name: str
    gravatar_url: str
    must_change_password: bool
    is_admin: bool
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class AzureAuthConfigRequest(BaseModel):
    client_id: str
    tenant_id: Optional[str] = ""
    client_secret: Optional[str] = None


class AzureConnectRequest(BaseModel):
    session_id: Optional[str] = None
    tenant_id: Optional[str] = None
    tenant_name: str = ""
    username: Optional[str] = None
    password: Optional[str] = None
    refresh_token: Optional[str] = None
    oauth_client_id: Optional[str] = None
    subscription_id: str


class AzureLoginRequest(BaseModel):
    username: str
    password: str


class SubscriptionInfo(BaseModel):
    id: str
    name: str
    state: str


class AzureLoginResponse(BaseModel):
    tenant_id: str
    tenant_name: str
    username: str
    subscriptions: list[SubscriptionInfo]
    validated: bool = True
    auth_type: str = "password"


class AzureConnectionResponse(BaseModel):
    tenant_id: str
    tenant_name: str = ""
    username: str
    subscription_id: str
    subscription_name: str
    connected: bool
    auth_type: str = "oauth"


class AzureDeviceStartResponse(BaseModel):
    session_id: str
    user_code: str
    verification_uri: str
    message: str
    expires_in: int


class AzureDevicePollRequest(BaseModel):
    session_id: str


class AzureBrowserStartRequest(BaseModel):
    redirect_uri: Optional[str] = None


class AzureBrowserStartResponse(BaseModel):
    session_id: str
    auth_url: str
    redirect_uri: str


class AzureAuthSessionResponse(BaseModel):
    session_id: str
    status: str
    tenant_id: str = ""
    tenant_name: str = ""
    username: str = ""
    subscriptions: list[SubscriptionInfo] = []
    error_message: Optional[str] = None


class VMDefinition(BaseModel):
    name: str
    os_type: str = Field(description="windows11 | windowsserver2025 | ubuntu")
    vm_size: Optional[str] = None
    admin_username: Optional[str] = None
    admin_password: Optional[str] = None


class VMConfigInput(BaseModel):
    name_prefix: str = Field(description="Préfixe de nom pour les VMs")
    os_type: str = Field(description="windows11 | windowsserver2025 | ubuntu")
    vm_size: Optional[str] = None
    quantity: int = Field(default=1, ge=1, le=100)
    admin_username: Optional[str] = None
    admin_password: Optional[str] = None


class WorkshopCreateRequest(BaseModel):
    name: str
    location: Optional[str] = None
    vms: list[VMConfigInput]
    duration_days: int = Field(default=5, ge=1, le=365)
    schedule_start_hour: int = 7
    schedule_stop_hour: int = 19
    schedule_timezone: str = "Europe/Paris"
    schedule_enabled: bool = True


class WorkshopResponse(BaseModel):
    id: int
    name: str
    slug: str
    resource_group: str
    location: str
    subscription_id: str
    vm_count: int
    schedule_start_hour: int
    schedule_stop_hour: int
    schedule_timezone: str
    schedule_enabled: bool
    duration_days: int
    status: str
    estimated_monthly_cost_eur: float
    estimated_monthly_cost_chf: float
    created_at: str
    created_by_user_id: Optional[int] = None
    created_by_username: Optional[str] = None
    created_by_display_name: Optional[str] = None
    created_by_email: Optional[str] = None

    class Config:
        from_attributes = True


class VMResponse(BaseModel):
    id: int
    workshop_id: int
    name: str
    os_type: str
    vm_size: str
    admin_username: str
    admin_password: str = ""
    public_ip: str
    private_ip: str
    remote_protocol: str
    remote_port: int
    power_state: str
    status: str
    provisioning_state: str = ""

    class Config:
        from_attributes = True


class VMCredentialsResponse(BaseModel):
    name: str
    admin_username: str
    admin_password: str
    public_ip: str
    remote_protocol: str
    remote_port: int


class CostEstimateRequest(BaseModel):
    location: str = "francecentral"
    vms: list[VMConfigInput]
    schedule_start_hour: int = 7
    schedule_stop_hour: int = 19
    duration_days: int = Field(default=5, ge=1, le=365)


class ExchangeRateResponse(BaseModel):
    eur_to_chf: float
    chf_to_eur: float
    updated_at: str
    source: str


class CostLineItem(BaseModel):
    resource: str
    unit: str
    quantity: float
    unit_price_eur: float
    monthly_cost_eur: float
    unit_price_chf: float
    monthly_cost_chf: float


class CostEstimateResponse(BaseModel):
    total_workshop_eur: float
    total_workshop_chf: float
    total_daily_eur: float
    total_daily_chf: float
    hours_per_day: float
    duration_days: int
    total_vm_count: int
    items: list[CostLineItem]
    exchange_rate: ExchangeRateResponse
    default_currency: str = "CHF"


class QuotePdfRequest(CostEstimateRequest):
    workshop_name: str = "Atelier Azure"
    client_name: str = ""
    currency: str = "CHF"
    cost_snapshot: CostEstimateResponse | None = None


class ConsumptionWorkshopDay(BaseModel):
    workshop_id: int
    workshop_name: str
    daily_cost_eur: float
    daily_cost_chf: float


class ConsumptionDayPoint(BaseModel):
    date: str
    daily_cost_eur: float
    daily_cost_chf: float
    cumulative_cost_eur: float
    cumulative_cost_chf: float
    active_workshop_count: int
    workshops: list[ConsumptionWorkshopDay]
    is_today: bool = False
    is_future: bool = False


class ConsumptionTimeline(BaseModel):
    start_date: str
    end_date: str
    today: str
    days: list[ConsumptionDayPoint]
    peak_daily_cost_eur: float
    peak_daily_cost_chf: float
    peak_date: str | None = None
    active_workshop_count: int = 0


class WorkshopMetrics(BaseModel):
    workshop_id: int
    workshop_name: str
    resource_group: str
    vm_count: int
    running_vms: int
    stopped_vms: int
    total_vcpu: int
    total_ram_gb: int
    estimated_monthly_cost_eur: float
    estimated_monthly_cost_chf: float


class SubscriptionMetrics(BaseModel):
    subscription_id: str
    subscription_name: str
    workshop_count: int
    total_vms: int
    running_vms: int
    total_vcpu: int
    total_ram_gb: int
    estimated_monthly_cost_eur: float
    estimated_monthly_cost_chf: float
    exchange_rate: ExchangeRateResponse
    default_currency: str = "CHF"
    workshops: list[WorkshopMetrics]
    consumption_timeline: ConsumptionTimeline | None = None
