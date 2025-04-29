from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Endpoint(db.Model):
    """Endpoint model representing the 'endpoints' table in the PostgreSQL database"""
    __tablename__ = 'endpoints'
    
    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(255), nullable=False)
    port = db.Column(db.Integer, nullable=False)
    scan_date = db.Column(db.DateTime, default=datetime.now)
    verified = db.Column(db.Integer, default=0)
    verification_date = db.Column(db.DateTime, nullable=True)
    is_honeypot = db.Column(db.Integer, default=0)
    honeypot_reason = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Integer, default=1)
    inactive_reason = db.Column(db.Text, nullable=True)
    last_check_date = db.Column(db.DateTime, nullable=True)
    
    # Relationship with models
    models = db.relationship('Model', backref='endpoint', lazy=True, cascade="all, delete-orphan")
    
    # Define a unique constraint on ip and port
    __table_args__ = (db.UniqueConstraint('ip', 'port', name='unique_ip_port'),)
    
    def __repr__(self):
        return f"<Endpoint {self.ip}:{self.port}>"
    
    @property
    def verified_str(self):
        return "Yes" if self.verified == 1 else "No"
    
    @property
    def is_honeypot_str(self):
        return "Yes" if self.is_honeypot == 1 else "No"
    
    @property
    def is_active_str(self):
        return "Yes" if self.is_active == 1 else "No"
        
    @property
    def model_count(self):
        return len(self.models)


class VerifiedEndpoint(db.Model):
    """VerifiedEndpoint model representing the 'verified_endpoints' table"""
    __tablename__ = 'verified_endpoints'
    
    id = db.Column(db.Integer, primary_key=True)
    endpoint_id = db.Column(db.Integer, db.ForeignKey('endpoints.id', ondelete='CASCADE'), unique=True)
    verification_date = db.Column(db.DateTime, default=datetime.now)
    
    def __repr__(self):
        return f"<VerifiedEndpoint {self.endpoint_id}>"


class Model(db.Model):
    """Model representing the 'models' table in the PostgreSQL database"""
    __tablename__ = 'models'
    
    id = db.Column(db.Integer, primary_key=True)
    endpoint_id = db.Column(db.Integer, db.ForeignKey('endpoints.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    parameter_size = db.Column(db.String(255), nullable=True)
    quantization_level = db.Column(db.String(255), nullable=True)
    size_mb = db.Column(db.Float, nullable=True)
    
    # Define a unique constraint on endpoint_id and name
    __table_args__ = (db.UniqueConstraint('endpoint_id', 'name', name='unique_endpoint_model'),)
    
    def __repr__(self):
        return f"<Model {self.name} on {self.endpoint_id}>"
