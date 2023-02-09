from pydantic import BaseSettings

class User(BaseSettings):
    id: str

class UserInfo(User):
    name: str
    url: str