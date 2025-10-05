from .database import db
from .models import Field, SatelliteMetrics, Advisory
from .utils import calculate_centroid, normalize_ndvi
from sentinelhub import SHConfig, SentinelHubRequest, DataCollection, MimeType, MosaickingOrder, BBox, CRS
from datetime import datetime, timedelta
import numpy as np
import requests
import json
import os
from typing import Dict, List
from sklearn.ensemble import RandomForestRegressor

class FieldAnalyzer:
    def __init__(self):
        self.config = SHConfig()
        self.config.sh_client_id = '74ddf553-4555-45ad-a379-14430e3ef19a'
        self.config.sh_client_secret = 'ntMnIssj7J4rgP7oHqdFPGriPoOWp9u4'
        self.weather_api_url = "https://power.larc.nasa.gov/api/temporal/daily/point"
        self.data_folder = './sentinel_data'
        os.makedirs(self.data_folder, exist_ok=True)
        self.health_model = None
        self.state_specific_data = {
            'Gujarat': {
                'pest_threshold': 0.4,
                'diseases': {
                    'Rice Blast': {'ndvi_threshold': 0.4, 'humidity_threshold': 75.0, 'temp_range': (25, 35), 'rainfall_threshold': 10.0},
                    'Bacterial Leaf Blight': {'ndvi_threshold': 0.45, 'humidity_threshold': 80.0, 'rainfall_threshold': 15.0}
                },
                'advisory_base': 'Check for {} due to high humidity in Gujarat.'
            },
            'Maharashtra': {
                'pest_threshold': 0.45,
                'diseases': {
                    'Powdery Mildew': {'ndvi_threshold': 0.45, 'humidity_threshold': 70.0, 'temp_range': (20, 30)},
                    'Downy Mildew': {'ndvi_threshold': 0.5, 'humidity_threshold': 85.0, 'rainfall_threshold': 15.0}
                },
                'advisory_base': 'Monitor {} in Maharashtra, especially during monsoon.'
            },
            'Rajasthan': {
                'pest_threshold': 0.35,
                'diseases': {
                    'Wilt': {'ndvi_threshold': 0.35, 'soil_moisture_threshold': 0.3, 'temp_range': (30, 40)},
                    'Root Rot': {'ndvi_threshold': 0.4, 'rainfall_threshold': 20.0}
                },
                'advisory_base': 'Watch for {} in dry Rajasthan conditions.'
            },
            'Punjab': {
                'pest_threshold': 0.5,
                'diseases': {
                    'Yellow Rust': {'ndvi_threshold': 0.5, 'humidity_threshold': 60.0, 'temp_range': (10, 25)},
                    'Karnal Bunt': {'ndvi_threshold': 0.45, 'rainfall_threshold': 10.0}
                },
                'advisory_base': 'Inspect for {} in Punjab wheat fields.'
            }
        }
        self.crop_thresholds = {
            'wheat': {'optimal_ndvi': (0.6, 0.85), 'temp_range': (15, 30), 'moisture_range': (0.3, 0.7)},
            'rice': {'optimal_ndvi': (0.65, 0.9), 'temp_range': (20, 35), 'moisture_range': (0.5, 0.8)},
            'cotton': {'optimal_ndvi': (0.55, 0.85), 'temp_range': (20, 35), 'moisture_range': (0.4, 0.7)},
            'sugarcane': {'optimal_ndvi': (0.7, 0.95), 'temp_range': (25, 35), 'moisture_range': (0.5, 0.8)},
            'maize': {'optimal_ndvi': (0.6, 0.9), 'temp_range': (20, 30), 'moisture_range': (0.4, 0.7)}
        }

    def train_health_model(self, field_id: int, days: int = 30):
        """Train RandomForest model for NDVI prediction."""
        df = self.get_field_history(field_id, days)
        if len(df['history']) < 5:
            return
        X = [[m['temp_mean'], m['rainfall_total'], m['humidity_mean'], m['wind_speed'], m['soil_moisture_est']]
             for m in df['history']]
        y = [m['ndvi_mean'] for m in df['history']]
        self.health_model = RandomForestRegressor(n_estimators=100, random_state=42)
        self.health_model.fit(X, y)

    def predict_health_trend(self, metrics: Dict) -> float:
        """Predict NDVI trend using trained model."""
        if self.health_model is None:
            return metrics.get('ndvi_mean', 0.5)
        features = [[
            metrics.get('temp_mean', 25.0),
            metrics.get('rainfall_total', 0.0),
            metrics.get('humidity_mean', 50.0),
            metrics.get('wind_speed_mean', 2.0),
            metrics.get('soil_moisture_est', 0.3)
        ]]
        return np.clip(self.health_model.predict(features)[0], 0.1, 0.95)

    def get_bbox_from_boundary(self, boundary: str) -> BBox:
        """Extract BBox from GeoJSON boundary."""
        data = json.loads(boundary)
        coords = data['coordinates'][0]
        min_x = min(c[0] for c in coords)
        max_x = max(c[0] for c in coords)
        min_y = min(c[1] for c in coords)
        max_y = max(c[1] for c in coords)
        return BBox(bbox=[min_x, min_y, max_x, max_y], crs=CRS.WGS84)

    def fetch_ndvi_data(self, bbox: BBox, time_interval: tuple) -> Dict:
        """Fetch NDVI data from Sentinel-2."""
        try:
            evalscript = """
            //VERSION=3
            function setup() {
                return {
                    input: ["B04", "B08", "CLM"],
                    output: { bands: 1 }
                };
            }
            function evaluatePixel(sample) {
                let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04);
                return [isNaN(ndvi) || sample.CLM > 0 ? null : ndvi];
            }
            """
            request = SentinelHubRequest(
                evalscript=evalscript,
                input_data=[SentinelHubRequest.input_data(
                    data_collection=DataCollection.SENTINEL2_L1C,
                    time_interval=time_interval,
                    mosaicking_order=MosaickingOrder.LEAST_CC
                )],
                responses=[SentinelHubRequest.output_response('default', MimeType.TIFF)],
                bbox=bbox,
                size=[512, 512],
                config=self.config
            )
            data = request.get_data()[0]
            valid_pixels = np.sum(~np.isnan(data))
            ndvi_values = data[~np.isnan(data)]
            return {
                'ndvi_mean': float(np.mean(ndvi_values)) if valid_pixels else 0.5,
                'ndvi_max': float(np.max(ndvi_values)) if valid_pixels else 0.6,
                'ndvi_min': float(np.min(ndvi_values)) if valid_pixels else 0.4,
                'cloud_coverage': float((np.sum(data == 0) / data.size) * 100) if valid_pixels else 0,
                'valid_pixels': int(valid_pixels),
                'image': data.tolist()
            }
        except Exception as e:
            print(f"Sentinel-2 error: {e}")
            return {
                'ndvi_mean': 0.5, 'ndvi_max': 0.6, 'ndvi_min': 0.4,
                'cloud_coverage': 0, 'valid_pixels': 1000
            }

    def fetch_soil_moisture(self, bbox: BBox, time_interval: tuple) -> float:
        """Fetch soil moisture estimate from Sentinel-1."""
        try:
            evalscript = """
            //VERSION=3
            function setup() {
                return {
                    input: ["VV", "VH"],
                    output: { bands: 1 }
                };
            }
            function evaluatePixel(sample) {
                return [(sample.VV - sample.VH) / (sample.VV + sample.VH)];
            }
            """
            request = SentinelHubRequest(
                evalscript=evalscript,
                input_data=[SentinelHubRequest.input_data(
                    data_collection=DataCollection.SENTINEL1_IW,
                    time_interval=time_interval
                )],
                responses=[SentinelHubRequest.output_response('default', MimeType.TIFF)],
                bbox=bbox,
                size=[512, 512],
                config=self.config
            )
            data = request.get_data()[0]
            return float(np.mean(data[~np.isnan(data)])) if np.any(~np.isnan(data)) else 0.3
        except Exception as e:
            print(f"Sentinel-1 error: {e}")
            return 0.3

    def fetch_weather_data(self, lat: float, lon: float, days: int = 7) -> Dict:
        """Fetch weather data from NASA POWER API."""
        try:
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            params = {
                'parameters': 'T2M,PRECTOTCORR,RH2M,WS2M',
                'community': 'AG',
                'longitude': lon,
                'latitude': lat,
                'start': start_date.strftime('%Y%m%d'),
                'end': end_date.strftime('%Y%m%d'),
                'format': 'JSON'
            }
            response = requests.get(self.weather_api_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()['properties']['parameter']
            return {
                'temp_mean': float(np.mean(list(data['T2M'].values()))),
                'rainfall_total': float(np.sum(list(data['PRECTOTCORR'].values()))),
                'humidity_mean': float(np.mean(list(data['RH2M'].values()))),
                'wind_speed_mean': float(np.mean(list(data['WS2M'].values())))
            }
        except Exception as e:
            print(f"Weather API error: {e}")
            return {
                'temp_mean': 25.0,
                'rainfall_total': 0.0,
                'humidity_mean': 50.0,
                'wind_speed_mean': 2.0
            }

    def determine_health_status(self, ndvi: float, state: str) -> str:
        """Determine crop health status with state-specific thresholds."""
        thresholds = self.state_specific_data.get(state, {'pest_threshold': 0.5})
        if ndvi > 0.7:
            return "Excellent"
        elif ndvi > thresholds['pest_threshold']:
            return "Good"
        elif ndvi > 0.3:
            return "Moderate"
        return "Poor"

    def generate_state_specific_advisories(self, field: Field, metrics: Dict) -> List[Dict]:
        """Generate state-specific and crop-specific advisories."""
        advisories = []
        state_data = self.state_specific_data.get(field.state, {})
        crop_data = self.crop_thresholds.get(field.crop_type, {})

        # State-specific pest/disease advisories
        if state_data:
            if metrics['ndvi_mean'] < state_data['pest_threshold']:
                advisories.append({
                    'level': 'warning',
                    'text': f"Pest risk high. NDVI below {state_data['pest_threshold']}."
                })
            for disease, cond in state_data['diseases'].items():
                risk = False
                if 'ndvi_threshold' in cond and metrics['ndvi_mean'] < cond['ndvi_threshold']:
                    risk = True
                if 'humidity_threshold' in cond and metrics['humidity_mean'] > cond['humidity_threshold']:
                    risk = True
                if 'temp_range' in cond and not (cond['temp_range'][0] <= metrics['temp_mean'] <= cond['temp_range'][1]):
                    risk = True
                if 'rainfall_threshold' in cond and metrics['rainfall_total'] > cond['rainfall_threshold']:
                    risk = True
                if 'soil_moisture_threshold' in cond and metrics['soil_moisture_est'] < cond['soil_moisture_threshold']:
                    risk = True
                if risk:
                    level = 'critical' if 'threshold' in disease.lower() else 'warning'
                    advisories.append({
                        'level': level,
                        'text': state_data['advisory_base'].format(disease)
                    })

        # Crop-specific advisories
        if crop_data:
            if metrics['ndvi_mean'] < crop_data['optimal_ndvi'][0]:
                advisories.append({
                    'level': 'critical',
                    'text': f"NDVI low for {field.crop_type}. Check nutrients/pests."
                })
            if not (crop_data['temp_range'][0] <= metrics['temp_mean'] <= crop_data['temp_range'][1]):
                advisories.append({
                    'level': 'warning',
                    'text': f"Temperature out of range for {field.crop_type}."
                })
            if metrics['soil_moisture_est'] < crop_data['moisture_range'][0]:
                advisories.append({
                    'level': 'critical',
                    'text': f"Irrigate: Soil moisture low for {field.crop_type}."
                })
            elif metrics['soil_moisture_est'] > crop_data['moisture_range'][1]:
                advisories.append({
                    'level': 'warning',
                    'text': f"Check drainage: Soil moisture high for {field.crop_type}."
                })

        # General advisories from cropadv.py
        if metrics['soil_moisture_est'] < 0.15:
            advisories.append({
                'level': 'critical',
                'text': "Irrigate immediately to raise soil moisture above 15%."
            })
        elif metrics['soil_moisture_est'] > 0.7:
            advisories.append({
                'level': 'warning',
                'text': "Reduce irrigation to lower soil moisture below 70%."
            })
        if metrics['temp_mean'] > 30:
            advisories.append({
                'level': 'warning',
                'text': "Implement shading or cooling measures for heat stress."
            })
        if not (isinstance(metrics['soil_moisture_est'], (int, float)) and 0 <= metrics['soil_moisture_est'] <= 1 and
                isinstance(metrics['temp_mean'], (int, float)) and 0 <= metrics['temp_mean'] <= 50):
            advisories.append({
                'level': 'critical',
                'text': "Check sensors for invalid data."
            })

        return advisories

    def analyze_field(self, field_id: int) -> Dict:
        """Analyze field data and store metrics with state-specific advisories."""
        field = Field.query.get(field_id)
        if not field or not field.boundary or not field.latitude or not field.longitude:
            raise ValueError("Field, boundary, latitude, or longitude not found")

        self.train_health_model(field_id)
        bbox = self.get_bbox_from_boundary(field.boundary)
        time_interval = (datetime.now() - timedelta(days=7), datetime.now())
        ndvi_data = self.fetch_ndvi_data(bbox, time_interval)
        soil_moisture = self.fetch_soil_moisture(bbox, time_interval)
        weather_data = self.fetch_weather_data(field.latitude, field.longitude)
        metrics = {
            **ndvi_data,
            **weather_data,
            'soil_moisture_est': soil_moisture,
            'evi_mean': 0.0  # Placeholder for EVI
        }
        health_status = self.determine_health_status(metrics['ndvi_mean'], field.state)
        predicted_ndvi = self.predict_health_trend(metrics)
        advisories = self.generate_state_specific_advisories(field, metrics)

        metric = SatelliteMetrics(
            field_id=field_id,
            date=datetime.now().date(),
            ndvi_mean=metrics['ndvi_mean'],
            ndvi_max=metrics['ndvi_max'],
            ndvi_min=metrics['ndvi_min'],
            evi_mean=metrics['evi_mean'],
            temp_mean=metrics['temp_mean'],
            rainfall_total=metrics['rainfall_total'],
            humidity_mean=metrics['humidity_mean'],
            wind_speed=metrics['wind_speed_mean'],
            cloud_coverage=metrics['cloud_coverage'],
            soil_moisture_est=metrics['soil_moisture_est'],
            data_source='Sentinel/NASA',
            valid_pixels=metrics['valid_pixels']
        )
        db.session.add(metric)
        db.session.commit()

        field.soil_moisture = metrics['soil_moisture_est']
        field.temperature = metrics['temp_mean']
        field.status = health_status
        db.session.commit()

        for adv in advisories:
            advisory = Advisory(
                field_id=field_id,
                metric_id=metric.metric_id,
                advisory_type='General',
                advisory_text=adv['text'],
                alert_level=adv['level'].upper(),
                priority=1 if adv['level'] == 'critical' else 2
            )
            db.session.add(advisory)
        db.session.commit()

        return {
            'success': True,
            'field_id': field_id,
            'metrics': metrics,
            'advisories': advisories,
            'health_status': health_status,
            'predicted_ndvi': predicted_ndvi
        }

    def get_field_history(self, field_id: int, days: int = 7) -> Dict:
        """Retrieve historical metrics for a field."""
        from_date = (datetime.now() - timedelta(days=days)).date()
        metrics = SatelliteMetrics.query.filter_by(field_id=field_id).filter(SatelliteMetrics.date >= from_date).all()
        return {
            'field_id': field_id,
            'history': [{
                'date': m.date.strftime('%Y-%m-%d'),
                'ndvi_mean': m.ndvi_mean,
                'temp_mean': m.temp_mean,
                'rainfall_total': m.rainfall_total,
                'humidity_mean': m.humidity_mean,
                'wind_speed': m.wind_speed,
                'soil_moisture_est': m.soil_moisture_est,
                'health_status': self.determine_health_status(m.ndvi_mean, Field.query.get(field_id).state)
            } for m in metrics]
        }