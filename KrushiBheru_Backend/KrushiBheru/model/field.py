from .database import db
from .models import Field
from .utils import validate_geojson, convert_coords, calculate_centroid, calculate_area, get_state_from_coords, get_district_from_coords
import json

class FieldManager:
    def __init__(self):
        self.db = db

    def create_field(self, user_id, name, boundary, area_ha=None, crop_type=None, crop_status=None, season=None,
                    latitude=None, longitude=None, state=None, district=None):
        """Create a new field with GeoJSON boundary and additional attributes."""
        if not all([user_id, name, boundary]):
            raise ValueError("Required fields (user_id, name, boundary) must be provided")
        if not validate_geojson(boundary):
            raise ValueError("Invalid GeoJSON boundary")
        
        # Convert boundary to string if dict
        if isinstance(boundary, dict):
            boundary = json.dumps(boundary)
        
        # Calculate centroid and area if not provided
        coords = convert_coords(boundary)
        if not latitude or not longitude:
            latitude, longitude = calculate_centroid(coords)
        if not area_ha:
            area_ha = calculate_area(coords)
        
        # Infer state and district if not provided
        if not state:
            state = get_state_from_coords(latitude, longitude)
        if not district:
            district = get_district_from_coords(latitude, longitude)
        
        try:
            field = Field(
                user_id=user_id,
                name=name,
                boundary=boundary,
                area_ha=area_ha,
                crop_type=crop_type,
                crop_status=crop_status,
                season=season,
                latitude=latitude,
                longitude=longitude,
                state=state,
                district=district
            )
            self.db.session.add(field)
            self.db.session.commit()
            return field.field_id
        except Exception as e:
            self.db.session.rollback()
            raise ValueError(f"Failed to create field: {str(e)}")

    def get_field(self, field_id):
        """Retrieve field by ID."""
        field = Field.query.get(field_id)
        if not field:
            raise ValueError("Field not found")
        return field

    def update_field(self, field_id, **kwargs):
        """Update existing field attributes."""
        field = self.get_field(field_id)
        for key, value in kwargs.items():
            if hasattr(field, key) and key != 'field_id':
                if key == 'boundary' and isinstance(value, dict):
                    if not validate_geojson(json.dumps(value)):
                        raise ValueError("Invalid GeoJSON boundary")
                    setattr(field, key, json.dumps(value))
                    # Update centroid and area
                    coords = convert_coords(json.dumps(value))
                    field.latitude, field.longitude = calculate_centroid(coords)
                    field.area_ha = calculate_area(coords)
                    if not field.state:
                        field.state = get_state_from_coords(field.latitude, field.longitude)
                    if not field.district:
                        field.district = get_district_from_coords(field.latitude, field.longitude)
                else:
                    setattr(field, key, value)
        try:
            self.db.session.commit()
            return field_id
        except Exception as e:
            self.db.session.rollback()
            raise ValueError(f"Failed to update field: {str(e)}")