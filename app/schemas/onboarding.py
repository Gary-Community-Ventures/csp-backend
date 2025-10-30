from pydantic import BaseModel, Field


class FamilyOnboardRequest(BaseModel):
    """Request schema for onboarding a family."""

    clerk_user_id: str = Field(..., min_length=1, description="Clerk user ID")
    family_id: str = Field(..., min_length=1, description="Family ID in Supabase")


class ProviderOnboardRequest(BaseModel):
    """Request schema for onboarding a provider."""

    clerk_user_id: str = Field(..., min_length=1, description="Clerk user ID")
    provider_id: str = Field(..., min_length=1, description="Provider ID in Supabase")


class OnboardResponse(BaseModel):
    """Response schema for successful onboarding."""

    message: str
    family_id: str | None = None
    provider_id: str | None = None
    clerk_user_id: str
