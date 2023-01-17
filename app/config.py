from pydantic import BaseSettings

class Settings(BaseSettings):
    ifttt_service_key: str

    auth0_domain: str
    auth0_audience: str
    issuer: str
    algorithms: str
    auth0_userinfo: str

    class Config:
        env_file = 'app/.env'
        env_file_encoding = 'utf-8'

settings = Settings()