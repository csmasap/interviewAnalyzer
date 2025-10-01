#!/usr/bin/env python3
"""
THEIA Interview Prep System - Credential Configuration Helper
Interactive script to help configure all necessary credentials.
"""

import os
import json
import subprocess
from pathlib import Path
from getpass import getpass

def print_header(title: str):
    """Print a formatted header"""
    print(f"\n{'='*60}")
    print(f"🔧 {title}")
    print('='*60)

def print_step(step: str, description: str):
    """Print a configuration step"""
    print(f"\n📝 {step}")
    print(f"   {description}")

def update_env_file(key: str, value: str):
    """Update .env file with new key-value pair"""
    env_file = Path(".env")
    
    if not env_file.exists():
        print("❌ .env file not found. Creating from template...")
        subprocess.run(["cp", "env.example", ".env"])
    
    # Read current content
    with open(env_file, 'r') as f:
        lines = f.readlines()
    
    # Update or add the key
    updated = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            updated = True
            break
    
    if not updated:
        lines.append(f"{key}={value}\n")
    
    # Write back to file
    with open(env_file, 'w') as f:
        f.writelines(lines)
    
    print(f"✅ Updated {key} in .env file")

def configure_google_cloud():
    """Configure Google Cloud credentials"""
    print_header("Google Cloud Platform Configuration")
    
    print_step("Step 1", "Google Cloud Project ID")
    print("You can find your project ID in the Google Cloud Console:")
    print("https://console.cloud.google.com/")
    
    project_id = input("Enter your Google Cloud Project ID: ").strip()
    if project_id:
        update_env_file("GOOGLE_CLOUD_PROJECT_ID", project_id)
    
    print_step("Step 2", "Service Account Key")
    print("You need to create a service account and download the JSON key file.")
    print("Place the JSON file in the 'credentials/' directory.")
    
    while True:
        key_path = input("Enter path to your service account JSON file (or press Enter to skip): ").strip()
        if not key_path:
            print("⚠️ Skipping service account key setup")
            break
        
        if Path(key_path).exists():
            # Copy to credentials directory
            credentials_dir = Path("credentials")
            credentials_dir.mkdir(exist_ok=True)
            
            dest_path = credentials_dir / "theia-service-account.json"
            subprocess.run(["cp", key_path, str(dest_path)])
            subprocess.run(["chmod", "600", str(dest_path)])
            
            update_env_file("GOOGLE_APPLICATION_CREDENTIALS", f"./credentials/theia-service-account.json")
            print(f"✅ Service account key copied to {dest_path}")
            break
        else:
            print(f"❌ File not found: {key_path}")
    
    print_step("Step 3", "Vertex AI Configuration")
    location = input(f"Enter Vertex AI location (default: us-central1): ").strip() or "us-central1"
    model = input(f"Enter Vertex AI model (default: gemini-1.5-pro): ").strip() or "gemini-1.5-pro"
    
    update_env_file("VERTEX_AI_LOCATION", location)
    update_env_file("VERTEX_AI_MODEL", model)

def configure_openai():
    """Configure OpenAI credentials"""
    print_header("OpenAI Configuration")
    
    print_step("Step 1", "OpenAI API Key")
    print("Get your API key from: https://platform.openai.com/api-keys")
    
    api_key = getpass("Enter your OpenAI API key (hidden input): ").strip()
    if api_key:
        if api_key.startswith("sk-"):
            update_env_file("OPENAI_API_KEY", api_key)
        else:
            print("⚠️ Warning: API key should start with 'sk-'")
            confirm = input("Continue anyway? (y/N): ").lower()
            if confirm == 'y':
                update_env_file("OPENAI_API_KEY", api_key)
    
    print_step("Step 2", "Realtime API Model")
    model = input("Enter Realtime API model (default: gpt-4o-realtime-preview-2024-10-01): ").strip()
    if model:
        update_env_file("OPENAI_REALTIME_MODEL", model)

def configure_salesforce():
    """Configure Salesforce credentials"""
    print_header("Salesforce Configuration")
    
    print_step("Step 1", "Salesforce Login Credentials")
    
    username = input("Enter your Salesforce username: ").strip()
    if username:
        update_env_file("SF_USERNAME", username)
    
    password = getpass("Enter your Salesforce password (hidden input): ").strip()
    if password:
        update_env_file("SF_PASSWORD", password)
    
    print_step("Step 2", "Salesforce Security Token")
    print("To get your security token:")
    print("1. Log into Salesforce")
    print("2. Go to Setup → My Personal Information → Reset My Security Token")
    print("3. Check your email for the new token")
    
    token = getpass("Enter your Salesforce security token (hidden input): ").strip()
    if token:
        update_env_file("SF_SECURITY_TOKEN", token)
    
    print_step("Step 3", "Salesforce Domain")
    domain = input("Enter Salesforce domain (default: login): ").strip() or "login"
    update_env_file("SF_DOMAIN", domain)

def configure_redis():
    """Configure Redis settings"""
    print_header("Redis Configuration")
    
    print_step("Step 1", "Redis Connection")
    print("Default Redis configuration should work for local development.")
    
    redis_url = input("Enter Redis URL (default: redis://localhost:6379/0): ").strip()
    if redis_url:
        update_env_file("REDIS_URL", redis_url)
    
    # Test Redis connection
    try:
        import redis
        client = redis.from_url(redis_url or "redis://localhost:6379/0")
        client.ping()
        print("✅ Redis connection successful")
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        print("Please ensure Redis is running:")
        print("  macOS: brew services start redis")
        print("  Linux: sudo systemctl start redis")

def main():
    """Main configuration function"""
    print("🚀 THEIA Interview Prep System - Credential Configuration")
    print("This script will help you configure all necessary credentials.")
    print("\n⚠️  Important: This script will modify your .env file")
    
    if not input("\nContinue? (y/N): ").lower().startswith('y'):
        print("Configuration cancelled.")
        return
    
    # Configure each service
    services = [
        ("Google Cloud Platform", configure_google_cloud),
        ("OpenAI", configure_openai),
        ("Salesforce", configure_salesforce),
        ("Redis", configure_redis)
    ]
    
    for service_name, configure_func in services:
        try:
            configure_func()
        except KeyboardInterrupt:
            print(f"\n⚠️ Skipping {service_name} configuration")
        except Exception as e:
            print(f"❌ Error configuring {service_name}: {e}")
    
    print_header("Configuration Complete")
    print("🎉 Credential configuration finished!")
    print("\n🧪 Next steps:")
    print("1. Run validation: python setup_validator.py")
    print("2. Start the system: ./start.sh")
    print("3. Test health check: curl http://localhost:8000/health")
    
    print("\n📁 Files created/updated:")
    print("   ✅ .env - Environment configuration")
    print("   ✅ credentials/ - Service account keys (if provided)")
    print("   ✅ .gitignore - Security exclusions")

if __name__ == "__main__":
    main()


