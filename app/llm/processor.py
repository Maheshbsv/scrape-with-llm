from datetime import datetime, date
import httpx
import json
import asyncio
from typing import List, Dict, Any, Optional
import re

from ..config.settings import settings
from ..utils.logger import get_logger
from ..scrapers.base_scraper import NotificationData
from .prompts import get_prompt
from .validators import ResponseValidator, ValidationError

# Initialize logger
logger = get_logger(__name__)

class LlamaProcessor:
    """Processor for LLM-based content extraction using Ollama"""
    
    def __init__(self, ollama_url: str = None, model: str = None):
        self.ollama_url = ollama_url or settings.ollama_url
        self.model = model or settings.llama_model
        self.client = httpx.AsyncClient(timeout=60.0)
        
        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 2
    
    async def health_check(self) -> bool:
        """Check if Ollama service is healthy"""
        try:
            response = await self.client.get(f"{self.ollama_url}/api/tags")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False
    
    async def ensure_model_available(self) -> bool:
        """Ensure the required model is available"""
        try:
            response = await self.client.get(f"{self.ollama_url}/api/tags")
            if response.status_code == 200:
                models = response.json()
                model_names = [model['name'] for model in models.get('models', [])]
                
                if self.model in model_names:
                    return True
                else:
                    logger.warning(f"Model {self.model} not found. Available models: {model_names}")
                    return False
            return False
        except Exception as e:
            logger.error(f"Failed to check model availability: {e}")
            return False
    
    async def extract_notifications(self, content: str, page_type: str = 'generic') -> List[NotificationData]:
        """Extract structured notification data using Llama"""
        if not content or len(content.strip()) < 50:
            logger.warning("Content too short for LLM processing")
            return []
        
        try:
            # Get prompt for notification extraction
            prompt_data = get_prompt('extract_notifications', text=content)
            
            # Call LLM with retry logic
            response = await self._call_ollama_with_retry(
                prompt_data['prompt'],
                prompt_data['system_context']
            )
            
            # Parse and validate response
            parsed_data = ResponseValidator.validate_json_structure(response)
            ResponseValidator.validate_output_format(parsed_data, prompt_data['output_format'])
            
            # Convert to NotificationData objects
            notifications = []
            for item in parsed_data.get('notifications', []):
                try:
                    validated_item = ResponseValidator.validate_notification(item)
                    notification = NotificationData(**validated_item)
                    notifications.append(notification)
                except ValidationError as e:
                    logger.warning(f"Skipping invalid notification: {e}")
            
            return notifications
            
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return []
    
    async def classify_page_type(self, content: str) -> str:
        """Classify page structure type using LLM"""
        try:
            # Use a shorter content sample for classification
            sample_content = content[:2000] if len(content) > 2000 else content
            
            # Get classification prompt
            prompt_data = get_prompt('classify_page', text=sample_content)
            
            # Call LLM
            response = await self._call_ollama_with_retry(
                prompt_data['prompt'],
                prompt_data['system_context']
            )
            
            # Parse and validate classification
            parsed_data = ResponseValidator.validate_json_structure(response)
            page_type = parsed_data.get('type', '').strip().lower()
            
            # Validate result
            valid_types = ['table', 'list', 'generic']
            if page_type in valid_types:
                return page_type
            
            return 'generic'  # Default to generic if classification is unclear
            
        except Exception as e:
            logger.error(f"Page classification failed: {e}")
            return 'generic'
    
    async def parse_date(self, date_string: str) -> Optional[date]:
        """Parse date string using LLM"""
        try:
            # Get date parsing prompt
            prompt_data = get_prompt(
                'parse_date',
                date_string=date_string,
                current_date=datetime.now().strftime('%Y-%m-%d')
            )
            
            # Call LLM
            response = await self._call_ollama_with_retry(
                prompt_data['prompt'],
                prompt_data['system_context']
            )
            
            # Parse and validate response
            parsed_data = ResponseValidator.validate_json_structure(response)
            date_str = parsed_data.get('date')
            
            if date_str:
                ResponseValidator.validate_date(date_str)
                return datetime.strptime(date_str, '%Y-%m-%d').date()
            
            return None
            
        except Exception as e:
            logger.error(f"Date parsing failed: {e}")
            return None
    
    async def _call_ollama_with_retry(self, prompt: str, system_context: str) -> str:
        """Call Ollama API with retry logic"""
        retries = 0
        last_error = None
        
        while retries < self.max_retries:
            try:
                response = await self.client.post(
                    f"{self.ollama_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "system": system_context,
                        "stream": False
                    },
                    timeout=60.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return result.get('response', '')
                
                raise httpx.HTTPError(f"API call failed with status {response.status_code}")
                
            except Exception as e:
                last_error = e
                retries += 1
                if retries < self.max_retries:
                    await asyncio.sleep(self.retry_delay * (2 ** (retries - 1)))  # Exponential backoff
        
        raise Exception(f"Failed after {self.max_retries} retries. Last error: {last_error}")