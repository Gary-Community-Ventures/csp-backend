from app.models import (
    AllocatedCareDay,
    AllocatedLumpSum,
    FamilyInvitation,
    MonthAllocation,
    PaymentRate,
    PaymentRequest,
    ProviderInvitation,
    ProviderPaymentSettings,
    Payment,
    PaymentAttempt,
    PaymentIntent,
)


class ModelAdminConfig:
    def __init__(self, model, name, category):
        self.model = model
        self.name = name
        self.category = category


ADMIN_MODELS = [
    ModelAdminConfig(PaymentRate, "Payment Rates", "Financial"),
    ModelAdminConfig(AllocatedCareDay, "Allocated Care Days", "Financial"),
    ModelAdminConfig(AllocatedLumpSum, "Allocated Lump Sums", "Financial"),
    ModelAdminConfig(MonthAllocation, "Month Allocations", "Financial"),
    ModelAdminConfig(PaymentRequest, "Payment Requests", "Financial"),
    ModelAdminConfig(ProviderInvitation, "Provider Invitations", "Users"),
    ModelAdminConfig(FamilyInvitation, "Family Invitations", "Users"),
    ModelAdminConfig(ProviderPaymentSettings, "Provider Payment Settings", "Financial"),
    ModelAdminConfig(Payment, "Payments", "Financial"),
    ModelAdminConfig(PaymentAttempt, "Payment Attempts", "Financial"),
    ModelAdminConfig(PaymentIntent, "Payment Intents", "Financial"),
]
