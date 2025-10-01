"""
Base Agent Class - Optimized Performance Foundation
Provides common functionality and performance optimizations for all THEIA agents.
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
from functools import lru_cache
from enum import Enum

import vertexai
from vertexai.generative_models import GenerativeModel
import json

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import settings

logger = logging.getLogger(__name__)


class TaskComplexity(Enum):
    """Task complexity levels for model selection"""
    SIMPLE = "simple"      # Use gemini-2.5-flash
    MODERATE = "moderate"  # Use gemini-2.5-pro with optimized params
    COMPLEX = "complex"    # Use gemini-2.5-pro with full params


class OptimizedAgent:
    """
    Base class for all THEIA agents with performance optimizations
    
    Key Features:
    - Intelligent model selection (flash vs pro)
    - Response caching with TTL
    - Optimized generation parameters
    - Concurrent execution support
    - Performance monitoring
    """
    
    def __init__(self, agent_name: str):
        """Initialize the optimized agent"""
        self.agent_name = agent_name
        self.project_id = settings.GOOGLE_CLOUD_PROJECT_ID
        self.location = settings.VERTEX_AI_LOCATION
        self.model_pro = settings.VERTEX_AI_MODEL  # gemini-2.5-pro
        self.model_flash = settings.VERTEX_AI_MODEL_FAST  # gemini-2.5-flash
        
        # Initialize Vertex AI
        if self.project_id:
            vertexai.init(project=self.project_id, location=self.location)
        
        # Initialize models
        self.models = {}
        self._initialize_models()
        
        # Performance tracking
        self.performance_stats = {
            "total_requests": 0,
            "cache_hits": 0,
            "flash_model_uses": 0,
            "pro_model_uses": 0,
            "average_response_time": 0.0
        }
        
        # Response cache (in-memory with TTL)
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes
    
    def _initialize_models(self):
        """Initialize both Vertex AI models"""
        try:
            self.models['flash'] = GenerativeModel(self.model_flash)
            self.models['pro'] = GenerativeModel(self.model_pro)
            logger.info(f"✅ {self.agent_name}: Initialized both models (flash & pro)")
        except Exception as e:
            logger.error(f"❌ {self.agent_name}: Failed to initialize models: {e}")
            self.models = {}
    
    def _get_generation_config(self, complexity: TaskComplexity, max_tokens: Optional[int] = None) -> Dict[str, Any]:
        """Get optimized generation parameters based on task complexity"""
        base_configs = {
            TaskComplexity.SIMPLE: {
                "temperature": 0.1,  # Very low for consistency
                "top_p": 0.7,
                "max_output_tokens": max_tokens or 1500,
                "candidate_count": 1,
            },
            TaskComplexity.MODERATE: {
                "temperature": 0.2,  # Low for consistency
                "top_p": 0.8,
                "max_output_tokens": max_tokens or 2500,
                "candidate_count": 1,
            },
            TaskComplexity.COMPLEX: {
                "temperature": 0.3,  # Moderate for creativity
                "top_p": 0.9,
                "max_output_tokens": max_tokens or 4000,
                "candidate_count": 1,
            }
        }
        return base_configs[complexity]
    
    def _select_model(self, complexity: TaskComplexity) -> GenerativeModel:
        """Select the appropriate model based on task complexity"""
        if complexity == TaskComplexity.SIMPLE:
            self.performance_stats["flash_model_uses"] += 1
            return self.models.get('flash')
        else:
            self.performance_stats["pro_model_uses"] += 1
            return self.models.get('pro')
    
    def _get_cache_key(self, prompt: str, complexity: TaskComplexity) -> str:
        """Generate cache key for prompt and complexity"""
        import hashlib
        content = f"{self.agent_name}:{complexity.value}:{prompt}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _get_cached_response(self, cache_key: str) -> Optional[str]:
        """Get cached response if still valid"""
        if cache_key in self._cache:
            response, timestamp = self._cache[cache_key]
            if time.time() - timestamp < self._cache_ttl:
                self.performance_stats["cache_hits"] += 1
                logger.info(f"🎯 {self.agent_name}: Cache hit for request")
                return response
            else:
                # Remove expired cache entry
                del self._cache[cache_key]
        return None
    
    def _cache_response(self, cache_key: str, response: str):
        """Cache response with timestamp"""
        self._cache[cache_key] = (response, time.time())
        
        # Simple cache cleanup - remove oldest entries if cache gets too large
        if len(self._cache) > 100:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
    
    async def generate_optimized(
        self,
        prompt: str,
        complexity: TaskComplexity = TaskComplexity.MODERATE,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
        use_cache: bool = True
    ) -> str:
        """
        Generate response with optimizations
        
        Args:
            prompt: The input prompt
            complexity: Task complexity level for model selection
            max_tokens: Maximum output tokens (overrides default)
            timeout: Custom timeout (overrides default)
            use_cache: Whether to use response caching
        """
        start_time = time.time()
        self.performance_stats["total_requests"] += 1
        
        # Check cache first
        cache_key = self._get_cache_key(prompt, complexity) if use_cache else None
        if cache_key:
            cached_response = self._get_cached_response(cache_key)
            if cached_response:
                return cached_response
        
        # Select model and config
        model = self._select_model(complexity)
        if not model:
            raise Exception(f"{self.agent_name}: Vertex AI models not initialized")
        
        generation_config = self._get_generation_config(complexity, max_tokens)
        
        # Set timeout based on complexity
        if not timeout:
            timeout_map = {
                TaskComplexity.SIMPLE: 30,      # 30 seconds for flash model
                TaskComplexity.MODERATE: 45,    # 45 seconds for moderate tasks
                TaskComplexity.COMPLEX: 60      # 60 seconds for complex tasks
            }
            timeout = timeout_map[complexity]
        
        try:
            logger.info(f"🚀 {self.agent_name}: Generating with {complexity.value} complexity")
            logger.info(f"🎯 Model: {self.model_flash if complexity == TaskComplexity.SIMPLE else self.model_pro}")
            
            # Generate response with timeout
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    model.generate_content,
                    prompt,
                    generation_config=generation_config
                ),
                timeout=timeout
            )
            
            response_text = response.text
            
            # Cache the response
            if cache_key:
                self._cache_response(cache_key, response_text)
            
            # Update performance stats
            response_time = time.time() - start_time
            self.performance_stats["average_response_time"] = (
                (self.performance_stats["average_response_time"] * (self.performance_stats["total_requests"] - 1) + response_time) /
                self.performance_stats["total_requests"]
            )
            
            logger.info(f"✅ {self.agent_name}: Response generated in {response_time:.2f}s")
            return response_text
            
        except asyncio.TimeoutError:
            logger.error(f"⏰ {self.agent_name}: Generation timed out after {timeout}s")
            raise Exception(f"Generation timed out after {timeout} seconds")
        except Exception as e:
            logger.error(f"❌ {self.agent_name}: Generation failed: {e}")
            raise
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for monitoring"""
        return {
            **self.performance_stats,
            "cache_size": len(self._cache),
            "cache_hit_rate": (
                self.performance_stats["cache_hits"] / max(self.performance_stats["total_requests"], 1) * 100
            ),
            "flash_usage_rate": (
                self.performance_stats["flash_model_uses"] / max(self.performance_stats["total_requests"], 1) * 100
            )
        }
    
    def clear_cache(self):
        """Clear the response cache"""
        self._cache.clear()
        logger.info(f"🧹 {self.agent_name}: Cache cleared")


# Utility functions for concurrent agent execution
async def run_agents_concurrently(agent_tasks: List[asyncio.Task]) -> List[Any]:
    """
    Run multiple agent tasks concurrently with error handling
    
    Args:
        agent_tasks: List of asyncio tasks to run concurrently
        
    Returns:
        List of results (successful results or exceptions)
    """
    try:
        results = await asyncio.gather(*agent_tasks, return_exceptions=True)
        return results
    except Exception as e:
        logger.error(f"❌ Concurrent agent execution failed: {e}")
        raise


def create_agent_task(agent_method, *args, **kwargs) -> asyncio.Task:
    """Create an asyncio task for agent method execution"""
    return asyncio.create_task(agent_method(*args, **kwargs))
