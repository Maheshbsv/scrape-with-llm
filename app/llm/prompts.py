from typing import Dict, Any
from dataclasses import dataclass

@dataclass
class PromptTemplate:
    """Template for LLM prompts"""
    template: str
    system_context: str
    output_format: Dict[str, Any]

# System context for notification extraction
NOTIFICATION_SYSTEM_CONTEXT = """You are a precise and accurate information extractor. Your task is to extract structured information about tenders, notifications, or empanelment opportunities from the given text. Focus on key details such as:
- Title or description of the tender/notification
- Tender ID or reference number
- Location information
- Category or type
- Important dates (start date, end date, submission deadline)
Extract only factual information present in the text. Do not make assumptions or add information not present in the text."""

# System context for date parsing
DATE_SYSTEM_CONTEXT = """You are a date parsing expert. Your task is to identify and convert date strings into a standardized YYYY-MM-DD format. Consider various date formats and contexts to accurately determine the date. If a date is ambiguous or invalid, return null."""

# Prompt templates for different tasks
PROMPTS = {
    'extract_notifications': PromptTemplate(
        template="""Analyze the following text and extract information about tenders or notifications:

{text}

Extract the information in the specified JSON format. If any field is not found, use null.""",
        system_context=NOTIFICATION_SYSTEM_CONTEXT,
        output_format={
            "notifications": [
                {
                    "title": "string",
                    "tender_id": "string | null",
                    "location": "string | null",
                    "category": "string | null",
                    "start_date": "YYYY-MM-DD | null",
                    "end_date": "YYYY-MM-DD | null",
                    "additional_info": "object | null"
                }
            ]
        }
    ),
    
    'classify_page': PromptTemplate(
        template="""Analyze the following page content and determine its structure type:

{text}

Classify the page as one of:
- table: Content is primarily in a tabular format
- list: Content is organized as a list of items
- generic: Content has no clear structural pattern

Return only the classification term.""",
        system_context="You are a web page structure analyzer. Your task is to classify pages based on their content structure.",
        output_format={"type": "string"}
    ),
    
    'parse_date': PromptTemplate(
        template="""Parse the following date string into YYYY-MM-DD format:

{date_string}

Consider the current date is {current_date} for resolving relative dates.
If the date is invalid or cannot be determined, return null.""",
        system_context=DATE_SYSTEM_CONTEXT,
        output_format={"date": "YYYY-MM-DD | null"}
    ),
    
    'extract_location': PromptTemplate(
        template="""Extract the location information from the following text:

{text}

Return the most specific location mentioned. Consider cities, districts, states, and regions.
If no location is found, return null.""",
        system_context="You are a location information extractor. Your task is to identify geographical locations in text.",
        output_format={"location": "string | null"}
    )
}

def get_prompt(prompt_type: str, **kwargs) -> Dict[str, Any]:
    """Get a formatted prompt with its system context and output format"""
    if prompt_type not in PROMPTS:
        raise ValueError(f"Unknown prompt type: {prompt_type}")
        
    template = PROMPTS[prompt_type]
    return {
        "prompt": template.template.format(**kwargs),
        "system_context": template.system_context,
        "output_format": template.output_format
    }