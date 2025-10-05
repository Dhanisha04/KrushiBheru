from .database import db
from .models import Field, SatelliteMetrics, Advisory
from .analysis import FieldAnalyzer
from datetime import datetime, timedelta
import os
import json
import pandas as pd
import folium
from folium.plugins import HeatMap
from typing import Dict, List

class ReportGenerator:
    def __init__(self):
        self.analyzer = FieldAnalyzer()
        self.output_dir = './reports'
        os.makedirs(self.output_dir, exist_ok=True)

    def _get_data(self, field_id: int, days: int = 7) -> Dict:
        """Fetch metrics, advisories, and field data."""
        try:
            field = Field.query.get(field_id)
            if not field or not field.boundary or not field.latitude or not field.longitude:
                raise ValueError("Field or required attributes not found")
            from_date = (datetime.now() - timedelta(days=days)).date()
            metrics = SatelliteMetrics.query.filter_by(field_id=field_id).filter(SatelliteMetrics.date >= from_date).all()
            advisories = Advisory.query.filter_by(field_id=field_id).filter(Advisory.metric_id.in_([m.metric_id for m in metrics])).all()
            if not metrics:
                raise ValueError("No metrics available for the specified period")
            latest = metrics[-1]
            return {
                'field': field,
                'latest': {
                    'date': latest.date,
                    'ndvi_mean': latest.ndvi_mean,
                    'temp_mean': latest.temp_mean,
                    'rainfall_total': latest.rainfall_total,
                    'humidity_mean': latest.humidity_mean,
                    'wind_speed': latest.wind_speed,
                    'soil_moisture_est': latest.soil_moisture_est,
                    'health_status': field.status  # From Field.status
                },
                'history': [{
                    'date': m.date.strftime('%Y-%m-%d'),
                    'ndvi_mean': m.ndvi_mean,
                    'temp_mean': m.temp_mean,
                    'rainfall_total': m.rainfall_total,
                    'humidity_mean': m.humidity_mean,
                    'wind_speed': m.wind_speed,
                    'soil_moisture_est': m.soil_moisture_est,
                    'health_status': field.status
                } for m in metrics],
                'advisories': [{
                    'level': a.alert_level.lower(),
                    'text': a.advisory_text,
                    'date': m.date.strftime('%Y-%m-%d') if (m := SatelliteMetrics.query.get(a.metric_id)) else datetime.now().strftime('%Y-%m-%d')
                } for a in advisories]
            }
        except Exception as e:
            raise ValueError(f"Failed to fetch data: {str(e)}")

    def _create_map(self, field_id: int) -> str:
        """Generate a Folium map with NDVI heatmap using Sentinel-2 data."""
        try:
            data = self._get_data(field_id)
            field = data['field']
            boundary = json.loads(field.boundary)['coordinates'][0]
            coords = [[c[1], c[0]] for c in boundary]  # Flip to [lat, lon]
            center = [field.latitude, field.longitude]
            
            # Fetch NDVI image data from analyzer
            analysis = self.analyzer.analyze_field(field_id)
            ndvi_image = analysis['metrics'].get('image', [])
            
            m = folium.Map(location=center, zoom_start=13, tiles='CartoDB positron')
            folium.Polygon(locations=coords, color='blue', fill=False, weight=2).add_to(m)
            
            # Create NDVI heatmap if image data is available
            if ndvi_image:
                height, width = len(ndvi_image), len(ndvi_image[0]) if ndvi_image else 0
                min_lon, min_lat, max_lon, max_lat = min(c[0] for c in boundary), min(c[1] for c in boundary), max(c[0] for c in boundary), max(c[1] for c in boundary)
                heat_data = []
                for i in range(height):
                    for j in range(width):
                        if not np.isnan(ndvi_image[i][j]):
                            lat = min_lat + (max_lat - min_lat) * (i / height)
                            lon = min_lon + (max_lon - min_lon) * (j / width)
                            heat_data.append([lat, lon, ndvi_image[i][j]])
                HeatMap(heat_data, radius=15, min_opacity=0.3, max_val=1.0).add_to(m)
            
            # Add CircleMarker for latest NDVI
            latest_ndvi = data['latest']['ndvi_mean']
            color = 'red' if latest_ndvi < 0.4 else 'green' if latest_ndvi > 0.6 else 'yellow'
            folium.CircleMarker(
                location=center,
                radius=10,
                color=color,
                fill=True,
                fill_color=color,
                popup=f"NDVI: {latest_ndvi:.2f} ({data['latest']['date']})"
            ).add_to(m)
            
            map_path = f"{self.output_dir}/map_{field_id}.html"
            m.save(map_path)
            return os.path.basename(map_path)
        except Exception as e:
            raise ValueError(f"Failed to create map: {str(e)}")

    def generate_technical_report(self, field_id: int) -> str:
        """Generate concise technical report."""
        try:
            data = self._get_data(field_id)
            map_file = self._create_map(field_id)
            report = (
                f"# Technical Report\n\n"
                f"**Field ID:** {field_id}\n"
                f"**Name:** {data['field'].name}\n"
                f"**State:** {data['field'].state or 'Unknown'}\n"
                f"**Crop Type:** {data['field'].crop_type or 'Unknown'}\n"
                f"**Date:** {data['latest']['date']}\n\n"
                f"## Metrics\n"
                f"- NDVI: {data['latest']['ndvi_mean']:.2f}\n"
                f"- Temperature: {data['latest']['temp_mean']:.1f}°C\n"
                f"- Rainfall: {data['latest']['rainfall_total']:.1f}mm\n"
                f"- Humidity: {data['latest']['humidity_mean']:.1f}%\n"
                f"- Soil Moisture: {data['latest']['soil_moisture_est']:.2f}\n"
                f"- Status: {data['latest']['health_status']}\n\n"
                f"## NDVI Trend\n" +
                "\n".join([f"- {h['date']}: NDVI = {h['ndvi_mean']:.2f}, Status = {h['health_status']}" for h in data['history']]) +
                f"\n\n## Advisories\n" +
                "\n".join([f"{i}. **{a['level'].upper()}:** {a['text']} ({a['date']})" for i, a in enumerate(data['advisories'], 1)]) or "No advisories.\n" +
                f"\n## Map\n[View Map]({map_file})"
            )
            report_path = f"{self.output_dir}/tech_report_{field_id}.md"
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report)
            return report
        except Exception as e:
            raise ValueError(f"Failed to generate technical report: {str(e)}")

    def generate_farmer_report(self, field_id: int) -> str:
        """Generate concise farmer-friendly report."""
        try:
            data = self._get_data(field_id)
            map_file = self._create_map(field_id)
            report = (
                f"# Farmer Advisory\n\n"
                f"**Hi {data['field'].name} Farmer!**\n"
                f"**Location:** {data['field'].state or 'Unknown'}, {data['field'].district or 'Unknown'}\n"
                f"**Crop:** {data['field'].crop_type or 'Unknown'}\n"
                f"**Date:** {data['latest']['date']}\n\n"
                f"## Update\n"
                f"- Health: {data['latest']['health_status'].lower()} (NDVI: {data['latest']['ndvi_mean']:.2f})\n"
                f"- Weather: {data['latest']['temp_mean']:.1f}°C, {data['latest']['humidity_mean']:.1f}%, {data['latest']['rainfall_total']:.1f}mm\n"
                f"- Soil Moisture: {data['latest']['soil_moisture_est']:.2f}\n\n"
                f"## Actions\n" +
                "\n".join([f"{i}. **{'URGENT' if a['level'] == 'critical' else 'CAUTION' if a['level'] == 'warning' else 'NOTE'}:** {a['text']} ({a['date']})" for i, a in enumerate(data['advisories'], 1)]) or "No actions needed. Great job!\n" +
                f"\n## Map\n[View Map]({map_file})"
            )
            report_path = f"{self.output_dir}/farmer_report_{field_id}.md"
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(report)
            return report
        except Exception as e:
            raise ValueError(f"Failed to generate farmer report: {str(e)}")

    def generate_json_report(self, field_id: int) -> Dict:
        """Generate JSON report with metrics and advisories."""
        try:
            data = self._get_data(field_id)
            report = {
                'field_id': field_id,
                'name': data['field'].name,
                'state': data['field'].state or 'Unknown',
                'crop_type': data['field'].crop_type or 'Unknown',
                'date': data['latest']['date'].strftime('%Y-%m-%d'),
                'metrics': {
                    'ndvi_mean': data['latest']['ndvi_mean'],
                    'temp_mean': data['latest']['temp_mean'],
                    'rainfall_total': data['latest']['rainfall_total'],
                    'humidity_mean': data['latest']['humidity_mean'],
                    'soil_moisture_est': data['latest']['soil_moisture_est'],
                    'health_status': data['latest']['health_status']
                },
                'history': data['history'],
                'advisories': data['advisories']
            }
            report_path = f"{self.output_dir}/report_{field_id}.json"
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2)
            return report
        except Exception as e:
            raise ValueError(f"Failed to generate JSON report: {str(e)}")

    def generate_csv_history(self, field_id: int) -> str:
        """Generate CSV file with historical metrics."""
        try:
            data = self._get_data(field_id)
            df = pd.DataFrame(data['history'])
            csv_path = f"{self.output_dir}/history_{field_id}.csv"
            df.to_csv(csv_path, index=False)
            return csv_path
        except Exception as e:
            raise ValueError(f"Failed to generate CSV history: {str(e)}")

    def generate_report(self, field_id: int) -> Dict:
        """Generate all reports and map, return result."""
        try:
            tech = self.generate_technical_report(field_id)
            farmer = self.generate_farmer_report(field_id)
            json_report = self.generate_json_report(field_id)
            csv_path = self.generate_csv_history(field_id)
            map_file = self._create_map(field_id)
            return {
                'success': True,
                'report': {
                    'metrics': tech,
                    'advisories': farmer,
                    'json': json_report,
                    'csv': os.path.basename(csv_path),
                    'map_file': map_file,
                    'history': self._get_data(field_id)['history']
                }
            }
        except ValueError as e:
            return {'success': False, 'message': str(e)}
        except Exception as e:
            return {'success': False, 'message': f"Server error: {str(e)}"}