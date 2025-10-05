-- Users table
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL,
    contact_no VARCHAR(20) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    state VARCHAR(100),
    district VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Field table
CREATE TABLE field (
    field_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name VARCHAR(255) NOT NULL,
    boundary TEXT NOT NULL,
    area_ha DECIMAL(10,4),
    perimeter_km DECIMAL(10,4),
    corners INTEGER,
    crop_type VARCHAR(100),
    crop_status VARCHAR(100),
    season VARCHAR(100),
    latitude DECIMAL(10,6),
    longitude DECIMAL(10,6),
    state VARCHAR(100),
    district VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE ON UPDATE CASCADE
);

-- Satellite metrics table
CREATE TABLE satellite_metrics (
    metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id INTEGER,
    date DATE,
    ndvi_mean DECIMAL(5,4),
    ndvi_max DECIMAL(5,4),
    ndvi_min DECIMAL(5,4),
    evi_mean DECIMAL(5,4),
    temp_mean DECIMAL(5,2),
    rainfall_total DECIMAL(8,2),
    humidity_mean DECIMAL(5,2),
    wind_speed DECIMAL(6,2),
    cloud_coverage DECIMAL(5,2),
    soil_moisture_est DECIMAL(5,2),
    data_source VARCHAR(255),
    valid_pixels INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (field_id) REFERENCES field(field_id) ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE(field_id, date)
);

-- Advisory table
CREATE TABLE advisory (
    advisory_id INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id INTEGER,
    metric_id INTEGER,
    advisory_type VARCHAR(100),
    advisory_text TEXT,
    alert_level VARCHAR(20) DEFAULT 'LOW',
    priority INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (field_id) REFERENCES field(field_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (metric_id) REFERENCES satellite_metrics(metric_id) ON DELETE SET NULL ON UPDATE CASCADE
);