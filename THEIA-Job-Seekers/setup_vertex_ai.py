#!/usr/bin/env python3
"""
THEIA Interview Prep System - Vertex AI Setup Helper
Interactive script specifically for setting up Google Cloud Vertex AI.
"""

import os
import subprocess
import json
from pathlib import Path

def print_header(title: str):
    """Print a formatted header"""
    print(f"\n{'='*60}")
    print(f"🔧 {title}")
    print('='*60)

def print_step(step_num: int, title: str, description: str):
    """Print a setup step"""
    print(f"\n📝 Step {step_num}: {title}")
    print(f"   {description}")

def run_command(command: str, description: str = ""):
    """Run a command and show the result"""
    if description:
        print(f"🔄 {description}")
    
    try:
        result = subprocess.run(command.split(), capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Success: {command}")
            if result.stdout.strip():
                print(f"   Output: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ Failed: {command}")
            if result.stderr.strip():
                print(f"   Error: {result.stderr.strip()}")
            return False
    except Exception as e:
        print(f"❌ Error running command: {e}")
        return False

def check_gcloud_installed():
    """Check if gcloud CLI is installed"""
    print_step(1, "Check Google Cloud CLI", "Verifying gcloud CLI installation")
    
    if run_command("gcloud version", "Checking gcloud version"):
        return True
    else:
        print("\n❌ Google Cloud CLI not found!")
        print("📥 Please install it first:")
        print("   macOS: brew install google-cloud-sdk")
        print("   Linux: Follow instructions at https://cloud.google.com/sdk/docs/install")
        print("   Windows: Download from https://cloud.google.com/sdk/docs/install")
        return False

def setup_project():
    """Setup Google Cloud project"""
    print_step(2, "Project Configuration", "Setting up your Google Cloud project")
    
    # Check current project
    result = subprocess.run(["gcloud", "config", "get-value", "project"], 
                          capture_output=True, text=True)
    
    if result.returncode == 0 and result.stdout.strip():
        current_project = result.stdout.strip()
        print(f"🔍 Current project: {current_project}")
        
        use_current = input(f"Use current project '{current_project}'? (Y/n): ").strip()
        if use_current.lower() not in ['n', 'no']:
            return current_project
    
    # List available projects
    print("\n📋 Available projects:")
    subprocess.run(["gcloud", "projects", "list", "--format=table(projectId,name,projectNumber)"])
    
    # Get project ID from user
    while True:
        project_id = input("\nEnter your Google Cloud Project ID: ").strip()
        if project_id:
            # Set the project
            if run_command(f"gcloud config set project {project_id}", f"Setting project to {project_id}"):
                return project_id
        else:
            print("❌ Please enter a valid project ID")

def enable_apis(project_id: str):
    """Enable required APIs"""
    print_step(3, "Enable APIs", "Enabling required Google Cloud APIs")
    
    apis = [
        ("aiplatform.googleapis.com", "Vertex AI API"),
        ("cloudresourcemanager.googleapis.com", "Cloud Resource Manager API"),
        ("iam.googleapis.com", "Identity and Access Management API")
    ]
    
    for api, description in apis:
        print(f"\n🔄 Enabling {description}...")
        if run_command(f"gcloud services enable {api}", f"Enabling {api}"):
            print(f"✅ {description} enabled")
        else:
            print(f"❌ Failed to enable {description}")
            return False
    
    return True

def create_service_account(project_id: str):
    """Create service account for THEIA"""
    print_step(4, "Service Account", "Creating service account for THEIA agents")
    
    service_account_name = "theia-interview-prep"
    service_account_email = f"{service_account_name}@{project_id}.iam.gserviceaccount.com"
    
    # Check if service account already exists
    result = subprocess.run([
        "gcloud", "iam", "service-accounts", "describe", service_account_email
    ], capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"✅ Service account already exists: {service_account_email}")
    else:
        # Create service account
        if not run_command(
            f"gcloud iam service-accounts create {service_account_name} --display-name='THEIA Interview Prep System'",
            "Creating service account"
        ):
            return None
    
    # Grant permissions
    roles = [
        "roles/aiplatform.user",
        "roles/aiplatform.serviceAgent"
    ]
    
    for role in roles:
        run_command(
            f"gcloud projects add-iam-policy-binding {project_id} --member=serviceAccount:{service_account_email} --role={role}",
            f"Granting {role}"
        )
    
    return service_account_email

def download_service_key(project_id: str, service_account_email: str):
    """Download service account key"""
    print_step(5, "Service Account Key", "Downloading authentication key")
    
    # Create credentials directory
    credentials_dir = Path("credentials")
    credentials_dir.mkdir(exist_ok=True)
    
    key_file = credentials_dir / "theia-service-account.json"
    
    # Download key
    if run_command(
        f"gcloud iam service-accounts keys create {key_file} --iam-account={service_account_email}",
        "Downloading service account key"
    ):
        # Secure the key file
        os.chmod(key_file, 0o600)
        print(f"✅ Service account key saved to: {key_file}")
        return str(key_file)
    else:
        print("❌ Failed to download service account key")
        return None

def update_env_file(project_id: str, credentials_path: str):
    """Update .env file with Vertex AI configuration"""
    print_step(6, "Environment Configuration", "Updating .env file")
    
    env_file = Path(".env")
    
    # Read current .env file
    if env_file.exists():
        with open(env_file, 'r') as f:
            lines = f.readlines()
    else:
        print("📝 Creating .env file from template...")
        subprocess.run(["cp", "env.example", ".env"])
        with open(env_file, 'r') as f:
            lines = f.readlines()
    
    # Update Google Cloud settings
    updates = {
        "GOOGLE_CLOUD_PROJECT_ID": project_id,
        "GOOGLE_APPLICATION_CREDENTIALS": credentials_path,
        "VERTEX_AI_LOCATION": "us-central1",
        "VERTEX_AI_MODEL": "gemini-1.5-pro"
    }
    
    for key, value in updates.items():
        updated = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}\n"
                updated = True
                break
        
        if not updated:
            lines.append(f"{key}={value}\n")
    
    # Write back to .env file
    with open(env_file, 'w') as f:
        f.writelines(lines)
    
    print("✅ .env file updated with Vertex AI configuration")

def test_setup():
    """Test the Vertex AI setup"""
    print_step(7, "Test Setup", "Validating Vertex AI configuration")
    
    try:
        from dotenv import load_dotenv
        load_dotenv()
        
        from google.cloud import aiplatform
        from google.cloud.aiplatform import generative_models
        
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID")
        location = os.getenv("VERTEX_AI_LOCATION")
        model_name = os.getenv("VERTEX_AI_MODEL")
        
        print(f"🧪 Testing configuration:")
        print(f"   Project: {project_id}")
        print(f"   Location: {location}")
        print(f"   Model: {model_name}")
        
        # Initialize and test
        aiplatform.init(project=project_id, location=location)
        model = generative_models.GenerativeModel(model_name)
        
        print("✅ Vertex AI setup successful!")
        print("🤖 All THEIA agents ready to use Google Cloud Vertex AI")
        return True
        
    except Exception as e:
        print(f"❌ Setup test failed: {e}")
        return False

def main():
    """Main setup function"""
    print("🚀 THEIA Interview Prep System - Vertex AI Setup")
    print("=" * 50)
    print("This script will help you set up Google Cloud Vertex AI")
    print("for the THEIA interview preparation agents.")
    
    if not input("\n🤔 Continue with Vertex AI setup? (Y/n): ").lower().startswith('n'):
        
        # Step 1: Check gcloud CLI
        if not check_gcloud_installed():
            return
        
        # Step 2: Setup project
        project_id = setup_project()
        if not project_id:
            print("❌ Failed to configure project")
            return
        
        # Step 3: Enable APIs
        if not enable_apis(project_id):
            print("❌ Failed to enable required APIs")
            return
        
        # Step 4: Create service account
        service_account_email = create_service_account(project_id)
        if not service_account_email:
            print("❌ Failed to create service account")
            return
        
        # Step 5: Download key
        credentials_path = download_service_key(project_id, service_account_email)
        if not credentials_path:
            print("❌ Failed to download service account key")
            return
        
        # Step 6: Update .env file
        update_env_file(project_id, credentials_path)
        
        # Step 7: Test setup
        if test_setup():
            print_header("🎉 Vertex AI Setup Complete!")
            print("✅ Google Cloud Vertex AI is ready for THEIA!")
            print("\n🚀 Next steps:")
            print("1. Configure other services: python configure_credentials.py")
            print("2. Validate full setup: python setup_validator.py")
            print("3. Start THEIA: ./start.sh")
        else:
            print("❌ Setup validation failed. Please check the configuration.")
    else:
        print("Setup cancelled.")

if __name__ == "__main__":
    main()


