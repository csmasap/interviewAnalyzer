# AI Skill Interview App

A standalone FastAPI application for conducting AI-powered skill-based interviews using OpenAI and Salesforce integration.

## Features

- **AI-Powered Skill Extraction**: Automatically identifies 7 most relevant skills from candidate resumes
- **Dynamic Question Generation**: Creates personalized interview questions based on extracted skills
- **Interactive Chat Interface**: Sequential question presentation with real-time responses
- **Complete Transcript Generation**: Full interview record with questions and answers
- **Salesforce Integration**: Reads candidate data from Salesforce Contact records
- **Standalone Operation**: Completely independent from other applications

## Architecture

### Two-Agent System
1. **Skill Extraction Agent**: Analyzes resume text to identify key skills
2. **Question Generation Agent**: Creates targeted interview questions based on skills

### Workflow Steps
1. **Resume Analysis** → Extract 7 skills from `Candidate_s_Resume_TXT__c`
2. **Question Generation** → Create 7 personalized questions
3. **Interactive Interview** → Present questions sequentially
4. **Transcript Generation** → Create complete interview record

## Setup

### Prerequisites
- Python 3.8+
- OpenAI API key
- Salesforce credentials

### Installation

1. **Clone and navigate to the skill interview app directory:**
   ```bash
   cd skill_interview_app
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your actual credentials
   ```

### Configuration

Edit the `.env` file with your credentials:

```env
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_BASE_URL=
OPENAI_TIMEOUT_SECONDS=30
OPENAI_MAX_RETRIES=3
OPENAI_MODEL=gpt-4

# Salesforce Configuration
SALESFORCE_USERNAME=your_salesforce_username
SALESFORCE_PASSWORD=your_salesforce_password
SALESFORCE_SECURITY_TOKEN=your_security_token
SALESFORCE_DOMAIN=login

# Application Configuration
LOG_LEVEL=INFO
ENVIRONMENT=dev
```

## Running the Application

### Development Mode
```bash
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8001
```

### Production Mode
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8001
```

### Using the Run Script
```bash
./run.sh
```

## Usage

1. **Access the application:**
   ```
   http://localhost:8001/?record_id=YOUR_CONTACT_ID
   ```

2. **Enter Salesforce Contact ID** (starts with 003)

3. **Start Interview** → System extracts skills from resume

4. **Generate Questions** → AI creates personalized questions

5. **Answer Questions** → Respond to each question sequentially

6. **View Transcript** → Complete interview record generated

## API Endpoints

- `GET /` - Main UI
- `POST /api/start` - Start interview (form data: `record_id`)
- `POST /api/generate-questions` - Generate questions (form data: `interview_id`)
- `POST /api/answer` - Submit answer (form data: `interview_id`, `answer`)
- `GET /api/status/{interview_id}` - Get interview status
- `GET /healthz` - Health check

## Project Structure

```
skill_interview_app/
├── src/
│   ├── main.py                 # FastAPI application
│   ├── config.py              # Configuration settings
│   ├── salesforce_client.py   # Salesforce integration
│   └── skill_interview_service.py  # Core business logic
├── templates/
│   └── index.html            # Main UI template
├── static/                   # Static files (CSS, JS, images)
├── requirements.txt          # Python dependencies
├── .env.example             # Environment template
├── README.md                # This file
└── run.sh                   # Run script
```

## Key Components

### SkillInterviewService
- Manages interview sessions in memory
- Coordinates with OpenAI for skill extraction and question generation
- Handles Salesforce integration for candidate data
- Generates comprehensive interview transcripts

### SalesforceClient
- Simplified client focused on Contact record queries
- Extracts resume text from `Candidate_s_Resume_TXT__c` field
- Handles authentication and connection management

### Configuration
- Environment-based configuration using Pydantic
- Separate settings for OpenAI, Salesforce, and app configuration
- Secure credential management

## Error Handling

- **Resume Not Found**: Clear error when Contact record lacks resume text
- **Invalid Contact ID**: Validation for Salesforce ID format
- **OpenAI Failures**: Fallback questions and skills when AI generation fails
- **Salesforce Errors**: Graceful handling of connection and query issues

## Security Considerations

- Environment variables for sensitive credentials
- Input validation for Contact IDs
- No persistent storage of interview data
- Secure API endpoints with proper error responses

## Development

### Adding New Features
1. Extend `SkillInterviewService` for new functionality
2. Add new API endpoints in `main.py`
3. Update UI in `templates/index.html`
4. Add configuration options in `config.py`

### Testing
- Use dummy Contact IDs for testing
- Mock Salesforce responses for development
- Test error scenarios and edge cases

## Deployment

### Docker
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8001
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

### Environment Variables
Ensure all required environment variables are set in production:
- `OPENAI_API_KEY`
- `SALESFORCE_USERNAME`
- `SALESFORCE_PASSWORD`
- `SALESFORCE_SECURITY_TOKEN`

## Troubleshooting

### Common Issues

1. **"No resume text found"**
   - Ensure Contact record has `Candidate_s_Resume_TXT__c` field populated
   - Verify Contact ID is correct and accessible

2. **OpenAI API errors**
   - Check `OPENAI_API_KEY` is set correctly
   - Verify API quota and billing status

3. **Salesforce connection errors**
   - Validate Salesforce credentials
   - Check network connectivity to Salesforce

### Logs
Check application logs for detailed error information:
```bash
tail -f logs/skill_interview.log
```

## License

This project is part of the Interview Analyzer system.