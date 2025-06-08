from typing import Dict, Any, List, Optional
from datetime import datetime
import re
import json

class ValidationError(Exception):
    """Custom exception for validation errors"""
    pass

class ResponseValidator:
    """Validator for LLM responses"""
    
    @staticmethod
    def validate_json_structure(response: str) -> Dict[str, Any]:
        """Validate and parse JSON response"""
        try:
            # Clean response to extract JSON
            json_str = ResponseValidator._extract_json(response)
            data = json.loads(json_str)
            return data
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON response: {str(e)}")
    
    @staticmethod
    def validate_notification(notification: Dict[str, Any]) -> Dict[str, Any]:
        """Validate notification data structure"""
        required_fields = ['title']
        optional_fields = ['tender_id', 'location', 'category', 'start_date', 'end_date', 'additional_info']
        
        # Check required fields
        for field in required_fields:
            if field not in notification or not notification[field]:
                raise ValidationError(f"Missing required field: {field}")
        
        # Validate dates if present
        if notification.get('start_date'):
            ResponseValidator.validate_date(notification['start_date'])
        if notification.get('end_date'):
            ResponseValidator.validate_date(notification['end_date'])
        
        # Remove any fields not in required or optional lists
        valid_fields = required_fields + optional_fields
        return {k: v for k, v in notification.items() if k in valid_fields}
    
    @staticmethod
    def validate_date(date_str: str) -> bool:
        """Validate date string format (YYYY-MM-DD)"""
        if not date_str:
            return True
            
        date_pattern = r'^\d{4}-\d{2}-\d{2}$'
        if not re.match(date_pattern, date_str):
            raise ValidationError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD")
            
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return True
        except ValueError as e:
            raise ValidationError(f"Invalid date value: {str(e)}")
    
    @staticmethod
    def validate_output_format(data: Dict[str, Any], expected_format: Dict[str, Any]) -> bool:
        """Validate response against expected output format"""
        try:
            ResponseValidator._validate_structure(data, expected_format)
            return True
        except ValidationError as e:
            raise ValidationError(f"Output format validation failed: {str(e)}")
    
    @staticmethod
    def _validate_structure(data: Any, expected: Any, path: str = '') -> None:
        """Recursively validate data structure against expected format"""
        if isinstance(expected, dict):
            if not isinstance(data, dict):
                raise ValidationError(f"Expected dict at {path}, got {type(data)}")
            for key, value in expected.items():
                if key not in data:
                    raise ValidationError(f"Missing key {key} at {path}")
                ResponseValidator._validate_structure(data[key], value, f"{path}.{key}")
        elif isinstance(expected, list):
            if not isinstance(data, list):
                raise ValidationError(f"Expected list at {path}, got {type(data)}")
            for i, item in enumerate(data):
                ResponseValidator._validate_structure(item, expected[0], f"{path}[{i}]")
        elif expected == "string | null":
            if data is not None and not isinstance(data, str):
                raise ValidationError(f"Expected string or null at {path}, got {type(data)}")
        elif expected == "object | null":
            if data is not None and not isinstance(data, dict):
                raise ValidationError(f"Expected dict or null at {path}, got {type(data)}")
    
    @staticmethod
    def _extract_json(response: str) -> str:
        """Extract JSON from LLM response"""
        # Try to find JSON between triple backticks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
        if json_match:
            return json_match.group(1)
        
        # Try to find JSON between curly braces
        json_match = re.search(r'({[\s\S]*})', response)
        if json_match:
            return json_match.group(1)
        
        # If no JSON markers found, return the whole response
        return response.strip()