"""Request and response bodies of the authentication API."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field

# compared and stored in lower case, so "Ciro@Example.com" and "ciro@example.com" are the same account
Email = Annotated[EmailStr, AfterValidator(str.lower)]


class RegisterIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: Email
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    home_airport: str = Field(pattern=r"^[A-Z]{3}$")


class LoginIn(BaseModel):
    email: Email
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    first_name: str
    last_name: str
    home_airport: str


class AirportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    iata: str
    city: str
    country: str