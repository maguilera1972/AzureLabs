import base64
import logging
import time
from typing import Optional

from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.compute.models import (
    AdditionalCapabilities,
    DiskCreateOptionTypes,
    HardwareProfile,
    ImageReference,
    LinuxConfiguration,
    ManagedDiskParameters,
    NetworkInterfaceReference,
    NetworkProfile,
    OSDisk,
    OSProfile,
    SecurityProfile,
    StorageAccountTypes,
    StorageProfile,
    UefiSettings,
    VirtualMachine,
    WindowsConfiguration,
)
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.network.models import (
    NetworkInterfaceIPConfiguration,
    NetworkSecurityGroup,
    PublicIPAddress,
    SecurityRule,
    Subnet,
    VirtualNetwork,
)
from azure.mgmt.resource import ResourceManagementClient

from app.azure.auth import (
    AzureCredentials,
    NESTED_VIRT_SIZES,
    OS_IMAGES,
    get_credential,
)
from app.config import settings
from app.crypto import generate_password

logger = logging.getLogger(__name__)


def _compute_client(creds: AzureCredentials) -> ComputeManagementClient:
    return ComputeManagementClient(get_credential(creds), creds.subscription_id)


def _network_client(creds: AzureCredentials) -> NetworkManagementClient:
    return NetworkManagementClient(get_credential(creds), creds.subscription_id)


def _resource_client(creds: AzureCredentials) -> ResourceManagementClient:
    return ResourceManagementClient(get_credential(creds), creds.subscription_id)


def _cloud_init(username: str, password: str) -> str:
    script = f"""#cloud-config
users:
  - name: {username}
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    lock_passwd: false
chpasswd:
  list: |
    {username}:{password}
  expire: false
ssh_pwauth: true
package_update: true
packages:
  - qemu-kvm
  - libvirt-daemon-system
runcmd:
  - systemctl enable --now ssh
  - modprobe kvm_intel 2>/dev/null || modprobe kvm_amd 2>/dev/null || true
"""
    return base64.b64encode(script.encode()).decode()


def create_resource_group(creds: AzureCredentials, name: str, location: str) -> None:
    client = _resource_client(creds)
    client.resource_groups.create_or_update(name, {"location": location})


def resource_group_exists(creds: AzureCredentials, name: str) -> bool:
    client = _resource_client(creds)
    try:
        client.resource_groups.get(name)
        return True
    except ResourceNotFoundError:
        return False
    except AzureError as e:
        if getattr(e, "status_code", None) == 404:
            return False
        raise


def delete_resource_group(creds: AzureCredentials, name: str) -> None:
    if not resource_group_exists(creds, name):
        logger.info("Resource group %s already deleted in Azure", name)
        return
    client = _resource_client(creds)
    poller = client.resource_groups.begin_delete(name)
    poller.result(timeout=900)


def _ensure_network(
    creds: AzureCredentials,
    rg: str,
    location: str,
    vnet_name: str = "vnet-lab",
    subnet_name: str = "subnet-lab",
) -> tuple[str, str]:
    net = _network_client(creds)

    net.virtual_networks.begin_create_or_update(
        rg,
        vnet_name,
        VirtualNetwork(
            location=location,
            address_space={"address_prefixes": ["10.0.0.0/16"]},
        ),
    ).result()

    net.subnets.begin_create_or_update(
        rg,
        vnet_name,
        subnet_name,
        Subnet(address_prefix="10.0.0.0/24"),
    ).result()

    nsg_name = "nsg-lab"
    net.network_security_groups.begin_create_or_update(
        rg,
        nsg_name,
        NetworkSecurityGroup(
            location=location,
            security_rules=[
                SecurityRule(
                    name="Allow-RDP",
                    priority=1000,
                    direction="Inbound",
                    access="Allow",
                    protocol="Tcp",
                    source_port_range="*",
                    destination_port_range="3389",
                    source_address_prefix="*",
                    destination_address_prefix="*",
                ),
                SecurityRule(
                    name="Allow-SSH",
                    priority=1001,
                    direction="Inbound",
                    access="Allow",
                    protocol="Tcp",
                    source_port_range="*",
                    destination_port_range="22",
                    source_address_prefix="*",
                    destination_address_prefix="*",
                ),
            ],
        ),
    ).result()

    return vnet_name, subnet_name


def provision_vm(
    creds: AzureCredentials,
    resource_group: str,
    location: str,
    vm_name: str,
    os_type: str,
    admin_username: Optional[str] = None,
    admin_password: Optional[str] = None,
    vm_size: Optional[str] = None,
) -> dict:
    if os_type not in OS_IMAGES:
        raise ValueError(f"OS non supporté: {os_type}")

    image = OS_IMAGES[os_type]
    size = vm_size or settings.default_vm_size
    if size not in NESTED_VIRT_SIZES:
        raise ValueError(
            f"Taille {size} ne supporte pas la virtualisation imbriquée. "
            f"Utilisez: {', '.join(sorted(NESTED_VIRT_SIZES))}"
        )

    username = admin_username or ("labuser" if image["os_type"] == "Linux" else "labadmin")
    password = admin_password or generate_password()

    vnet_name, subnet_name = _ensure_network(creds, resource_group, location)
    net = _network_client(creds)

    pip_name = f"pip-{vm_name}"
    pip_poller = net.public_ip_addresses.begin_create_or_update(
        resource_group,
        pip_name,
        PublicIPAddress(
            location=location,
            sku={"name": "Standard"},
            public_ip_allocation_method="Static",
        ),
    )
    pip = pip_poller.result()

    nic_name = f"nic-{vm_name}"
    nic_poller = net.network_interfaces.begin_create_or_update(
        resource_group,
        nic_name,
        {
            "location": location,
            "ip_configurations": [
                NetworkInterfaceIPConfiguration(
                    name="ipconfig1",
                    subnet={"id": f"/subscriptions/{creds.subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Network/virtualNetworks/{vnet_name}/subnets/{subnet_name}"},
                    public_ip_address={"id": pip.id},
                )
            ],
            "network_security_group": {
                "id": f"/subscriptions/{creds.subscription_id}/resourceGroups/{resource_group}/providers/Microsoft.Network/networkSecurityGroups/nsg-lab"
            },
        },
    )
    nic = nic_poller.result()

    os_profile = OSProfile(
        computer_name=vm_name[:15],
        admin_username=username,
        admin_password=password,
    )

    if image["os_type"] == "Linux":
        os_profile.linux_configuration = LinuxConfiguration(
            disable_password_authentication=False,
        )
        os_profile.custom_data = _cloud_init(username, password)
    else:
        os_profile.windows_configuration = WindowsConfiguration(
            enable_automatic_updates=True,
            provision_vm_agent=True,
        )

    vm_params = VirtualMachine(
        location=location,
        hardware_profile=HardwareProfile(vm_size=size),
        storage_profile=StorageProfile(
            image_reference=ImageReference(
                publisher=image["publisher"],
                offer=image["offer"],
                sku=image["sku"],
                version=image["version"],
            ),
            os_disk=OSDisk(
                create_option=DiskCreateOptionTypes.from_image,
                managed_disk=ManagedDiskParameters(
                    storage_account_type=StorageAccountTypes.premium_lrs,
                ),
                disk_size_gb=128,
            ),
        ),
        os_profile=os_profile,
        network_profile=NetworkProfile(
            network_interfaces=[NetworkInterfaceReference(id=nic.id)]
        ),
        security_profile=SecurityProfile(
            security_type="TrustedLaunch",
            uefi_settings=UefiSettings(
                secure_boot_enabled=True,
                v_tpm_enabled=True,
            ),
        ),
        additional_capabilities=AdditionalCapabilities(ultra_ssd_enabled=False),
        tags={
            "lab-console": "true",
            "os-type": os_type,
            "nested-virt": "enabled",
        },
    )

    compute = _compute_client(creds)
    poller = compute.virtual_machines.begin_create_or_update(
        resource_group, vm_name, vm_params
    )
    vm = poller.result()

    private_ip = ""
    if nic.ip_configurations:
        private_ip = nic.ip_configurations[0].private_ip_address or ""

    return {
        "name": vm_name,
        "azure_vm_id": vm.id or "",
        "admin_username": username,
        "admin_password": password,
        "public_ip": pip.ip_address or "",
        "private_ip": private_ip,
        "vm_size": size,
        "os_type": os_type,
        "remote_protocol": image["remote_protocol"],
        "remote_port": image["remote_port"],
        "power_state": "running",
        "status": "provisioned",
    }


def get_vm_states(creds: AzureCredentials, resource_group: str, vm_name: str) -> tuple[str, str]:
    compute = _compute_client(creds)
    provisioning = "unknown"
    power = "unknown"
    try:
        view = compute.virtual_machines.instance_view(resource_group, vm_name)
        for status in view.statuses or []:
            if not status.code:
                continue
            if status.code.startswith("ProvisioningState/"):
                provisioning = status.code.split("/", 1)[1]
            elif status.code.startswith("PowerState/"):
                power = status.code.split("/", 1)[1]
    except AzureError:
        pass
    return provisioning, power


def get_vm_power_state(creds: AzureCredentials, resource_group: str, vm_name: str) -> str:
    return get_vm_states(creds, resource_group, vm_name)[1]


def start_vm(creds: AzureCredentials, resource_group: str, vm_name: str) -> None:
    _compute_client(creds).virtual_machines.begin_start(resource_group, vm_name).result()


def stop_vm(creds: AzureCredentials, resource_group: str, vm_name: str) -> None:
    _compute_client(creds).virtual_machines.begin_power_off(resource_group, vm_name).result()


def list_vms_in_group(creds: AzureCredentials, resource_group: str) -> list[dict]:
    compute = _compute_client(creds)
    results = []
    for vm in compute.virtual_machines.list(resource_group):
        name = vm.name or ""
        provisioning, power = get_vm_states(creds, resource_group, name)
        size = vm.hardware_profile.vm_size if vm.hardware_profile else ""
        results.append({
            "name": name,
            "vm_size": size,
            "power_state": power,
            "provisioning_state": provisioning,
            "os_type": (vm.tags or {}).get("os-type", "unknown"),
            "azure_vm_id": vm.id or "",
        })
    return results


def wait_for_resource_group_deletion(creds: AzureCredentials, name: str, timeout: int = 600) -> bool:
    client = _resource_client(creds)
    start = time.time()
    while time.time() - start < timeout:
        try:
            client.resource_groups.get(name)
            time.sleep(10)
        except AzureError:
            return True
    return False
