from app.models import (
    AllocatedCareDay,
    AllocatedLumpSum,
    FamilyInvitation,
    FamilyPaymentSettings,
    MonthAllocation,
    Payment,
    PaymentAttempt,
    PaymentIntent,
    PaymentRate,
    PaymentRequest,
    ProviderInvitation,
    ProviderPaymentSettings,
)


class ModelAdminConfig:
    def __init__(self, model, name, category, view_class=None):
        self.model = model
        self.name = name
        self.category = category
        self.view_class = view_class


ADMIN_MODELS = [
    ModelAdminConfig(PaymentRate, "Payment Rates", "Financial"),
    ModelAdminConfig(AllocatedCareDay, "Allocated Care Days", "Financial"),
    ModelAdminConfig(AllocatedLumpSum, "Allocated Lump Sums", "Financial"),
    ModelAdminConfig(MonthAllocation, "Month Allocations", "Financial"),
    ModelAdminConfig(PaymentRequest, "Payment Requests", "Financial"),
    ModelAdminConfig(ProviderInvitation, "Provider Invitations", "Users"),
    ModelAdminConfig(FamilyInvitation, "Family Invitations", "Users"),
    ModelAdminConfig(ProviderPaymentSettings, "Provider Payment Settings", "Financial"),
    ModelAdminConfig(FamilyPaymentSettings, "Family Payment Settings", "Financial"),
    ModelAdminConfig(Payment, "Payments", "Financial", "PaymentAdminView"),
    ModelAdminConfig(PaymentAttempt, "Payment Attempts", "Financial", "PaymentAttemptAdminView"),
    ModelAdminConfig(PaymentIntent, "Payment Intents", "Financial", "PaymentIntentAdminView"),
]
