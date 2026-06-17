from app.schemas import VMConfigInput, VMDefinition
from app.crypto import generate_password

OS_DEFAULT_PREFIX = {
    "windows11": "win11",
    "windowsserver2025": "win2025",
    "ubuntu": "ubuntu",
}

OS_DEFAULT_USER_BASE = {
    "windows11": "labwin",
    "windowsserver2025": "labws",
    "ubuntu": "labux",
}


def default_prefix_for_os(os_type: str) -> str:
    return OS_DEFAULT_PREFIX.get(os_type, "vm")


def _sanitize(value: str, max_len: int = 20) -> str:
    import re
    value = re.sub(r"[^a-zA-Z0-9-]", "-", value.strip())
    value = re.sub(r"-+", "-", value).strip("-")
    return value[:max_len] or "vm"


def expand_vm_configs(configs: list[VMConfigInput]) -> list[VMDefinition]:
    """Expand VM configuration lines with quantity into individual VMs with unique credentials."""
    expanded: list[VMDefinition] = []
    for cfg in configs:
        qty = max(1, min(cfg.quantity, 100))
        prefix = _sanitize(cfg.name_prefix or default_prefix_for_os(cfg.os_type))

        user_base = _sanitize(cfg.admin_username or OS_DEFAULT_USER_BASE.get(cfg.os_type, "lab"), 12)

        for i in range(1, qty + 1):
            name = f"{prefix}-{i:02d}" if qty > 1 else prefix
            if qty > 1:
                username = f"{user_base}{i:02d}"
            else:
                username = user_base

            expanded.append(VMDefinition(
                name=name[:64],
                os_type=cfg.os_type,
                vm_size=cfg.vm_size,
                admin_username=username[:32],
                admin_password=generate_password(),
            ))
    return expanded


def total_vm_count(configs: list[VMConfigInput]) -> int:
    return sum(max(1, min(c.quantity, 100)) for c in configs)
