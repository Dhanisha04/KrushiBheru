from .database import db
from datetime import datetime

class User(db.Model):
    __tablename__ = 'users'

    user_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    contact_no = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    state = db.Column(db.String(100))
    district = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    fields = db.relationship('Field', backref='user', cascade="all, delete-orphan", lazy=True)

    def __repr__(self):
        return f"<User {self.name}>"

class Field(db.Model):
    __tablename__ = 'field'

    field_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.user_id', ondelete='CASCADE', onupdate='CASCADE'))
    name = db.Column(db.String(255), nullable=False)
    boundary = db.Column(db.Text, nullable=False)  # GeoJSON as text
    area_ha = db.Column(db.Float)
    crop_type = db.Column(db.String(100))
    crop_status = db.Column(db.String(100))
    season = db.Column(db.String(100))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    state = db.Column(db.String(100))
    district = db.Column(db.String(100))
    soil_moisture = db.Column(db.Float)
    temperature = db.Column(db.Float)
    status = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    metrics = db.relationship('SatelliteMetrics', backref='field', cascade="all, delete-orphan", lazy=True)
    advisories = db.relationship('Advisory', backref='field', cascade="all, delete-orphan", lazy=True)

    def __repr__(self):
        return f"<Field {self.name}>"

class SatelliteMetrics(db.Model):
    __tablename__ = 'satellite_metrics'

    metric_id = db.Column(db.Integer, primary_key=True)
    field_id = db.Column(db.Integer, db.ForeignKey('field.field_id', ondelete='CASCADE', onupdate='CASCADE'))
    date = db.Column(db.Date)
    ndvi_mean = db.Column(db.Float)
    ndvi_max = db.Column(db.Float)
    ndvi_min = db.Column(db.Float)
    evi_mean = db.Column(db.Float)
    temp_mean = db.Column(db.Float)
    rainfall_total = db.Column(db.Float)
    humidity_mean = db.Column(db.Float)
    wind_speed = db.Column(db.Float)
    cloud_coverage = db.Column(db.Float)
    soil_moisture_est = db.Column(db.Float)
    data_source = db.Column(db.String(255))
    valid_pixels = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    advisories = db.relationship('Advisory', backref='metric', cascade="all, delete-orphan", lazy=True)

    def __repr__(self):
        return f"<SatelliteMetrics Field:{self.field_id} Date:{self.date}>"

class Advisory(db.Model):
    __tablename__ = 'advisory'

    advisory_id = db.Column(db.Integer, primary_key=True)
    field_id = db.Column(db.Integer, db.ForeignKey('field.field_id', ondelete='CASCADE', onupdate='CASCADE'))
    metric_id = db.Column(db.Integer, db.ForeignKey('satellite_metrics.metric_id', ondelete='SET NULL', onupdate='CASCADE'))
    advisory_type = db.Column(db.String(100))
    advisory_text = db.Column(db.Text)
    alert_level = db.Column(db.String(20), default='INFO')  # Supports CRITICAL, WARNING, INFO
    priority = db.Column(db.Integer, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Advisory {self.advisory_type} - {self.alert_level}>"