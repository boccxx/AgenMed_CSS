#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LLM client module - unified large model call interface"""

import time
import logging
import json
from typing import Dict, List, Optional
from openai import OpenAI
import httpx


class LLMClient:
    """LLM client, unified management of large model API calls"""
    
    def __init__(self, config: Dict):
        """
        Initialize LLM client
        
        Args:
            config: Configuration dictionary, containing api_key, model, etc.
        """
        self.logger = logging.getLogger(__name__)
        self.config = config  
        
        timeout_seconds = config.get('timeout', 600)
        client_kwargs = {
            'api_key': config['openai_api_key'],
            'timeout': httpx.Timeout(timeout_seconds, connect=30, read=timeout_seconds, write=30)
        }
        if 'api_base' in config:
            client_kwargs['base_url'] = config['api_base']
        self.client = OpenAI(**client_kwargs)
        
        self.model = config['model']
        self.temperature = config.get('temperature', 0.1)
        self.max_tokens = config.get('max_tokens', 8000)
        self.default_max_retries = config.get('max_retries', 3)
    
    def call(
        self,
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
        model: Optional[str] = None,
        max_retries: Optional[int] = None
    ) -> str:
        """
        Call LLM API, support retry mechanism
        
        Args:
            system_prompt: System prompt
            user_prompt: User prompt
            messages: Complete message list (if provided, system_prompt and user_prompt are ignored)
            model: Model name (optional, default using model in configuration)
            max_retries: Maximum retry次数 (optional, default using configuration value)
            
        Returns:
            Text content returned by LLM
            
        Raises:
            ValueError: If parameters are invalid
            Exception: If retry times exhausted and still failed
        """

        if messages is None and (system_prompt is None or user_prompt is None):
            raise ValueError("Must provide messages or (system_prompt and user_prompt)")
        
        if messages is None:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        
        model = model or self.model
        max_retries = max_retries if max_retries is not None else self.default_max_retries
        
        for attempt in range(max_retries):
            try:
                start_time = time.time()
                self.logger.info(f"Starting LLM call (model={model}, attempt={attempt+1}/{max_retries})...")
                
                try:
                    response = self.client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens
                    )
                except Exception as api_error:
                    elapsed = time.time() - start_time
                    if elapsed > 580:
                        raise TimeoutError(f"LLM API call exceeded timeout threshold ({elapsed:.1f}s)") from api_error
                    raise
                
                elapsed = time.time() - start_time
                self.logger.info(f"LLM response completed, time taken: {elapsed:.1f} seconds")

                if not response or not response.choices:
                    raise ValueError("API response is empty or invalid")
                
                if not response.choices[0] or not response.choices[0].message:
                    raise ValueError("API response format exception: missing message field")
                
                content = response.choices[0].message.content
                
                if content is None:
                    raise ValueError("API response content is empty")
                
                self.logger.info(f"LLM call successful (model={model}, attempt={attempt+1}, tokens: {response.usage.total_tokens if hasattr(response, 'usage') and response.usage else 'N/A'})")
                return content
                
            except Exception as e:
                error_msg = str(e)
                error_type = type(e).__name__
                
                if "Expecting value" in error_msg or "JSON" in error_msg or "JSONDecodeError" in error_type:
                    self.logger.warning(
                        f"LLM call failed (attempt {attempt + 1}/{max_retries}): {error_type} - API response parsing error (usually temporary network problem, retrying automatically)"
                    )
                    if attempt >= max_retries - 2:  
                        import traceback
                        self.logger.debug(f"Detailed error: {error_msg}\nError stack:\n{traceback.format_exc()}")
                elif "timeout" in error_msg.lower() or "timed out" in error_msg.lower() or "TimeoutError" in error_type:
                    self.logger.warning(
                        f"LLM call failed (attempt {attempt + 1}/{max_retries}): {error_type} - API request timeout"
                    )
                    if attempt == max_retries - 1:
                        self.logger.error(f"LLM call final failure after {max_retries} attempts: timeout")
                        raise TimeoutError(f"LLM call timeout after {max_retries} attempts")
                elif "rate limit" in error_msg.lower() or "429" in error_msg:
                    self.logger.warning(
                        f"LLM call failed (attempt {attempt + 1}/{max_retries}): {error_type} - API rate limit, waiting to retry"
                    )
                else:
                    self.logger.warning(
                        f"LLM call failed (attempt {attempt + 1}/{max_retries}): {error_type} - {error_msg}"
                    )
                
                if attempt == max_retries - 1:
                    self.logger.error(f"LLM call final failure: {e}")
                    raise
                
                wait_time = 2 ** attempt
                self.logger.info(f"Waiting {wait_time} seconds to retry...")
                time.sleep(wait_time)
        
        raise Exception("LLM call failed")



