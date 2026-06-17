import logging

from azure.mgmt.automation import AutomationClient
from azure.mgmt.automation.models import (
    JobScheduleCreateParameters,
    RunbookCreateOrUpdateParameters,
    ScheduleCreateOrUpdateParameters,
)

from app.azure.auth import AzureCredentials, get_credential

logger = logging.getLogger(__name__)

START_RUNBOOK = '''param(
    [string]$ResourceGroupName
)
$connectionName = "AzureRunAsConnection"
try {
    $servicePrincipalConnection = Get-AutomationConnection -Name $connectionName
    Connect-AzAccount -ServicePrincipal -TenantId $servicePrincipalConnection.TenantId `
        -ApplicationId $servicePrincipalConnection.ApplicationId `
        -CertificateThumbprint $servicePrincipalConnection.CertificateThumbprint
} catch {
    if (!$servicePrincipalConnection) {
        $ErrorMessage = "Connection $connectionName not found."
        throw $ErrorMessage
    } else {
        Write-Error -Message $_.Exception
        throw $_.Exception
    }
}
$vms = Get-AzVM -ResourceGroupName $ResourceGroupName | Where-Object {$_.Tags["lab-console"] -eq "true"}
foreach ($vm in $vms) {
    Start-AzVM -ResourceGroupName $ResourceGroupName -Name $vm.Name -NoWait
    Write-Output "Started $($vm.Name)"
}
'''

STOP_RUNBOOK = '''param(
    [string]$ResourceGroupName
)
$connectionName = "AzureRunAsConnection"
try {
    $servicePrincipalConnection = Get-AutomationConnection -Name $connectionName
    Connect-AzAccount -ServicePrincipal -TenantId $servicePrincipalConnection.TenantId `
        -ApplicationId $servicePrincipalConnection.ApplicationId `
        -CertificateThumbprint $servicePrincipalConnection.CertificateThumbprint
} catch {
    if (!$servicePrincipalConnection) {
        $ErrorMessage = "Connection $connectionName not found."
        throw $ErrorMessage
    } else {
        Write-Error -Message $_.Exception
        throw $_.Exception
    }
}
$vms = Get-AzVM -ResourceGroupName $ResourceGroupName | Where-Object {$_.Tags["lab-console"] -eq "true"}
foreach ($vm in $vms) {
    Stop-AzVM -ResourceGroupName $ResourceGroupName -Name $vm.Name -Force -NoWait
    Write-Output "Stopped $($vm.Name)"
}
'''


def _automation_client(creds: AzureCredentials) -> AutomationClient:
    return AutomationClient(get_credential(creds), creds.subscription_id)


def setup_workshop_schedules(
    creds: AzureCredentials,
    resource_group: str,
    location: str,
    start_hour: int,
    stop_hour: int,
    timezone: str = "Europe/Paris",
) -> dict:
    """Configure Azure Automation schedules for VM start/stop."""
    account_name = f"auto-{resource_group[:40].lower().replace('_', '-')}"
    client = _automation_client(creds)

    try:
        client.automation_account.create_or_update(
            resource_group,
            account_name,
            {
                "location": location,
                "sku": {"name": "Basic"},
                "tags": {"lab-console": "true"},
            },
        )

        client.runbook.create_or_update(
            resource_group,
            account_name,
            "Start-LabVMs",
            RunbookCreateOrUpdateParameters(
                location=location,
                log_verbose=True,
                log_progress=True,
                runbook_type="PowerShell",
                publish=True,
                description="Démarrage des VMs d'atelier",
                script=START_RUNBOOK,
            ),
        )

        client.runbook.create_or_update(
            resource_group,
            account_name,
            "Stop-LabVMs",
            RunbookCreateOrUpdateParameters(
                location=location,
                log_verbose=True,
                log_progress=True,
                runbook_type="PowerShell",
                publish=True,
                description="Arrêt des VMs d'atelier",
                script=STOP_RUNBOOK,
            ),
        )

        start_schedule = client.schedule.create_or_update(
            resource_group,
            account_name,
            "schedule-start",
            ScheduleCreateOrUpdateParameters(
                description=f"Démarrage quotidien à {start_hour}h",
                start_time=_next_run_time(start_hour),
                interval=1,
                frequency="Day",
                time_zone_id=timezone,
            ),
        )

        stop_schedule = client.schedule.create_or_update(
            resource_group,
            account_name,
            "schedule-stop",
            ScheduleCreateOrUpdateParameters(
                description=f"Arrêt quotidien à {stop_hour}h",
                start_time=_next_run_time(stop_hour),
                interval=1,
                frequency="Day",
                time_zone_id=timezone,
            ),
        )

        client.job_schedule.create(
            resource_group,
            account_name,
            JobScheduleCreateParameters(
                runbook={"name": "Start-LabVMs"},
                schedule={"name": start_schedule.name},
                parameters={"ResourceGroupName": resource_group},
            ),
        )

        client.job_schedule.create(
            resource_group,
            account_name,
            JobScheduleCreateParameters(
                runbook={"name": "Stop-LabVMs"},
                schedule={"name": stop_schedule.name},
                parameters={"ResourceGroupName": resource_group},
            ),
        )

        return {
            "automation_account": account_name,
            "start_hour": start_hour,
            "stop_hour": stop_hour,
            "timezone": timezone,
            "status": "configured",
        }
    except Exception as e:
        logger.warning("Automation setup failed (manual scheduling may be needed): %s", e)
        return {
            "automation_account": account_name,
            "start_hour": start_hour,
            "stop_hour": stop_hour,
            "timezone": timezone,
            "status": "pending",
            "message": str(e),
        }


def _next_run_time(hour: int) -> str:
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target.strftime("%Y-%m-%dT%H:%M:%S+00:00")
