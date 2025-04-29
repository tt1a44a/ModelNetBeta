import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Base configuration class"""
    
    # Secret key for CSRF protection
    SECRET_KEY = os.getenv('SECRET_KEY', 'secret-key-for-dev-only')
    
    # Database URI
    SQLALCHEMY_DATABASE_URI = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
    
    # Configure SQLAlchemy to not track modifications
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Debug mode
    DEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 't')

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False

# Set the active configuration
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

active_config = config[os.getenv('FLASK_ENV', 'default')]
