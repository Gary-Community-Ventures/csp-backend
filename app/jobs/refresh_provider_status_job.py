from datetime import datetime, timezone

from flask import current_app

from app.extensions import db
from app.models.provider_payment_settings import ProviderPaymentSettings

from . import job_manager


@job_manager.job
def refresh_provider_status_job(provider_payment_settings_id: str, from_info: str = "unknown"):
    """
    Background job to refresh provider status from Chek API.

    Args:
        provider_payment_settings_id: UUID of the ProviderPaymentSettings record
        from_info: Source that triggered this refresh
    """
    try:
        current_app.logger.info(f"Refreshing provider status for {provider_payment_settings_id} from {from_info}")

        # Get the provider payment settings
        provider_payment_settings = ProviderPaymentSettings.query.filter_by(id=provider_payment_settings_id).first()

        if not provider_payment_settings:
            current_app.logger.error(f"Provider payment settings {provider_payment_settings_id} not found")
            return {"status": "error", "message": "Provider not found"}

        # Use the payment service to refresh the status
        payment_service = current_app.payment_service
        payment_service.refresh_provider_status(provider_payment_settings)

        # Update last sync time
        provider_payment_settings.last_chek_sync_at = datetime.now(timezone.utc)
        db.session.commit()

        current_app.logger.info(f"Successfully refreshed provider status for {provider_payment_settings_id}")

        return {
            "status": "success",
            "provider_id": provider_payment_settings.provider_external_id,
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
            "from_info": from_info,
        }

    except Exception as e:
        current_app.logger.error(f"Failed to refresh provider status for {provider_payment_settings_id}: {str(e)}")
        raise


def enqueue_provider_status_refresh(provider_payment_settings: ProviderPaymentSettings, from_info: str = "stale_check"):
    """
    Helper function to enqueue a provider status refresh job.

    Args:
        provider_payment_settings: ProviderPaymentSettings object to refresh
        from_info: Source that triggered this refresh
    """
    return refresh_provider_status_job.delay(
        provider_payment_settings_id=str(provider_payment_settings.id), from_info=from_info
    )
