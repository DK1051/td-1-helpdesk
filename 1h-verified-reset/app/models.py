"""Request bodies (what callers send). Pydantic rejects anything malformed with 422."""

from enum import Enum

from pydantic import BaseModel, Field


class Kind(str, Enum):
    password = "password"
    mfa_reset = "mfa_reset"
    mfa_enrol_device = "mfa_enrol_device"
    mfa_change_phone = "mfa_change_phone"


# These three change how someone proves who they are, so rule 5 watches them.
MFA_KINDS = {Kind.mfa_reset, Kind.mfa_enrol_device, Kind.mfa_change_phone}


class CreateResetRequest(BaseModel):
    kind: Kind
    claimed_username: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    # Only used by kind=mfa_change_phone: the new number to store.
    new_phone: str | None = Field(default=None, pattern=r"^\d{3}-\d{4}$")


class CallbackBody(BaseModel):
    number_dialed: str
    reached: bool


class OtpBody(BaseModel):
    code: str


class MfaChangeEvent(BaseModel):
    username: str = Field(min_length=1)
    change: str = Field(min_length=1)
    source: str = Field(min_length=1)
