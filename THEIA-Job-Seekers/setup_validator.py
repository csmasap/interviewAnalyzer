#!/usr/bin/env python3
"""
THEIA Interview Prep System - Setup Validator
This script helps validate your configuration and credentials setup.
"""

import os
import sys
import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def print_header(title: str):
    """Print a formatted header"""
    print(f"\n{'='*60}")
    print(f"🔍 {title}")
    print('='*60)

def print_status(service: str, status: str, details: str = ""):
    """Print service status"""
    emoji = "✅" if status == "OK" else "❌" if status == "ERROR" else "⚠️"
    print(f"{emoji} {service:<20} {status}")
    if details:
        print(f"   └─ {details}")

async def validate_google_cloud():
    """Validate Google Cloud configuration"""
    print_header("Google Cloud Platform Configuration")
    
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    location = os.getenv("VERTEX_AI_LOCATION", "us-central1")
    model = os.getenv("VERTEX_AI_MODEL", "gemini-1.5-pro")
    
    # Check project ID
    if not project_id:
        print_status("Project ID", "ERROR", "GOOGLE_CLOUD_PROJECT_ID not set")
        return False
    else:
        print_status("Project ID", "OK", project_id)
    
    # Check credentials file
    if not credentials_path:
        print_status("Credentials", "WARNING", "GOOGLE_APPLICATION_CREDENTIALS not set - will use default auth")
    else:
        if Path(credentials_path).exists():
            print_status("Credentials", "OK", f"File found: {credentials_path}")
        else:
            print_status("Credentials", "ERROR", f"File not found: {credentials_path}")
            return False
    
    # Test Vertex AI connection
    try:
        from google.cloud import aiplatform
        from google.cloud.aiplatform import generative_models
        
        aiplatform.init(project=project_id, location=location)
        model_instance = generative_models.GenerativeModel(model)
        print_status("Vertex AI", "OK", f"Model: {model}")
        return True
        
    except ImportError:
        print_status("Vertex AI", "ERROR", "Google Cloud libraries not installed")
        return False
    except Exception as e:
        print_status("Vertex AI", "ERROR", str(e))
        return False

async def validate_openai():
    """Validate OpenAI configuration"""
    print_header("OpenAI Configuration")
    
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_REALTIME_MODEL", "gpt-4o-realtime-preview-2024-10-01")
    
    # Check API key
    if not api_key:
        print_status("API Key", "ERROR", "OPENAI_API_KEY not set")
        return False
    elif not api_key.startswith("sk-"):
        print_status("API Key", "ERROR", "Invalid API key format")
        return False
    else:
        print_status("API Key", "OK", f"Key: ...{api_key[-8:]}")
    
    # Test OpenAI connection
    try:
        import openai
        client = openai.OpenAI(api_key=api_key)
        
        # Test basic API access
        models = client.models.list()
        print_status("OpenAI API", "OK", f"Connected successfully")
        print_status("Realtime Model", "OK", model)
        
        # Note: Realtime API testing requires WebSocket connection
        print_status("Realtime API", "INFO", "WebSocket testing required for full validation")
        return True
        
    except ImportError:
        print_status("OpenAI API", "ERROR", "OpenAI library not installed")
        return False
    except Exception as e:
        print_status("OpenAI API", "ERROR", str(e))
        return False

async def validate_salesforce():
    """Validate Salesforce configuration"""
    print_header("Salesforce Configuration")
    
    username = os.getenv("SF_USERNAME")
    password = os.getenv("SF_PASSWORD") 
    token = os.getenv("SF_SECURITY_TOKEN")
    domain = os.getenv("SF_DOMAIN", "login")
    
    # Check credentials
    if not username:
        print_status("Username", "ERROR", "SF_USERNAME not set")
        return False
    else:
        print_status("Username", "OK", username)
    
    if not password:
        print_status("Password", "ERROR", "SF_PASSWORD not set")
        return False
    else:
        print_status("Password", "OK", "Password set")
    
    if not token:
        print_status("Security Token", "ERROR", "SF_SECURITY_TOKEN not set")
        return False
    else:
        print_status("Security Token", "OK", f"Token: ...{token[-4:]}")
    
    # Test Salesforce connection
    try:
        from simple_salesforce import Salesforce
        
        sf = Salesforce(
            username=username,
            password=password,
            security_token=token,
            domain=domain
        )
        
        # Test connection with a simple query
        result = sf.query("SELECT Id FROM Contact LIMIT 1")
        print_status("Connection", "OK", f"Connected to {domain}.salesforce.com")
        
        # Check for THEIA_Interview__c object
        try:
            sf.describe()['sobjects']
            # Try to describe the custom object
            theia_obj = sf.THEIA_Interview__c.describe()
            print_status("THEIA Object", "OK", "THEIA_Interview__c object found")
        except Exception as e:
            print_status("THEIA Object", "WARNING", "THEIA_Interview__c object may not exist")
        
        return True
        
    except ImportError:
        print_status("Salesforce", "ERROR", "simple-salesforce library not installed")
        return False
    except Exception as e:
        print_status("Salesforce", "ERROR", str(e))
        return False

async def validate_redis():
    """Validate Redis configuration"""
    print_header("Redis Configuration")
    
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    try:
        import redis
        
        # Test Redis connection
        redis_client = redis.from_url(redis_url)
        redis_client.ping()
        print_status("Redis Connection", "OK", redis_url)
        
        # Test different databases for Celery
        celery_broker = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
        celery_result = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
        
        broker_client = redis.from_url(celery_broker)
        broker_client.ping()
        print_status("Celery Broker", "OK", celery_broker)
        
        result_client = redis.from_url(celery_result)
        result_client.ping()
        print_status("Celery Results", "OK", celery_result)
        
        return True
        
    except ImportError:
        print_status("Redis", "ERROR", "redis library not installed")
        return False
    except Exception as e:
        print_status("Redis", "ERROR", str(e))
        return False

async def validate_python_environment():
    """Validate Python environment and dependencies"""
    print_header("Python Environment")
    
    # Check Python version
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 11):
        print_status("Python Version", "OK", python_version)
    else:
        print_status("Python Version", "WARNING", f"{python_version} (3.11+ recommended)")
    
    # Check virtual environment
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print_status("Virtual Environment", "OK", "Active")
    else:
        print_status("Virtual Environment", "WARNING", "Not detected")
    
    # Check key dependencies
    dependencies = [
        ("fastapi", "FastAPI framework"),
        ("google.cloud.aiplatform", "Google Cloud Vertex AI"),
        ("openai", "OpenAI API client"),
        ("redis", "Redis client"),
        ("simple_salesforce", "Salesforce API client"),
        ("pydantic", "Data validation"),
        ("uvicorn", "ASGI server")
    ]
    
    all_deps_ok = True
    for dep_name, description in dependencies:
        try:
            __import__(dep_name)
            print_status(description, "OK", f"'{dep_name}' imported successfully")
        except ImportError:
            print_status(description, "ERROR", f"'{dep_name}' not installed")
            all_deps_ok = False
    
    return all_deps_ok

def print_summary(results: dict):
    """Print validation summary"""
    print_header("Configuration Summary")
    
    total_services = len(results)
    successful_services = sum(1 for success in results.values() if success)
    
    print(f"📊 Services Configured: {successful_services}/{total_services}")
    
    if successful_services == total_services:
        print("🎉 All services configured successfully!")
        print("🚀 Ready to start THEIA Interview Prep System")
        print("\n💡 Next steps:")
        print("   1. Run: ./start.sh")
        print("   2. Test: curl http://localhost:8000/health")
        print("   3. View API docs: http://localhost:8000/docs")
    else:
        print("⚠️  Some services need configuration:")
        for service, success in results.items():
            if not success:
                print(f"   ❌ {service}")
        print("\n🔧 Please fix the issues above before starting the system")

async def main():
    """Main validation function"""
    print("🚀 THEIA Interview Prep System - Configuration Validator")
    print("This script will validate your setup and credentials...")
    
    # Validate each service
    results = {}
    results["Python Environment"] = await validate_python_environment()
    results["Redis"] = await validate_redis()
    results["Google Cloud"] = await validate_google_cloud()
    results["OpenAI"] = await validate_openai()
    results["Salesforce"] = await validate_salesforce()
    
    # Print summary
    print_summary(results)

if __name__ == "__main__":
    asyncio.run(main())


