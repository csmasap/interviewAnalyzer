# THEIA Interview Prep System

THEIA (The Right People - Interview Preparation Agent) is an AI-powered interview preparation system that conducts mock interviews via both text and voice channels to help job seekers prepare effectively for real interviews.

## 🎯 **System Overview**

THEIA provides comprehensive interview preparation through:
- **Text-based interviews** using Google Vertex AI agents
- **Voice-to-voice interviews** using OpenAI Realtime API
- **Company research** and market intelligence
- **Skills assessment** and competency analysis
- **Dynamic question generation** based on job descriptions
- **Comprehensive evaluation** and feedback

## 🏗️ **Architecture**

```
┌─────────────────────────────────────────────────────────────────┐
│                    THEIA INTERVIEWER SYSTEM                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐  │
│  │  React Frontend │    │ FastAPI Backend │    │ Salesforce  │  │
│  │                 │    │                 │    │             │  │
│  │ - Text UI       │◄──►│ - Session Mgmt  │◄──►│ - Contacts  │  │
│  │ - Voice UI      │    │ - WebSocket Hub │    │ - Interviews│  │
│  │ - Mode Selection│    │ - Agent Orchestr│    │             │  │
│  └─────────────────┘    └─────────────────┘    └─────────────┘  │
│           │                       │                              │
│           │              ┌─────────────────┐                    │
│           │              │ Background Tasks│                    │
│           │              │    (Celery)     │                    │
│           │              │                 │                    │
│           │              └─────────────────┘                    │
│           │                       │                              │
│           ▼                       ▼                              │
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │ OpenAI Realtime │    │ Google Vertex AI│                    │
│  │  Voice Agent    │    │   Text Agents   │                    │
│  │                 │    │                 │                    │
│  │ ISA_Prep_Voice  │    │ ISA_Researcher  │                    │
│  │                 │    │ ISA_Detector    │                    │
│  │                 │    │ ISA_Questioner  │                    │
│  │                 │    │ ISA_Evaluator   │                    │
│  └─────────────────┘    └─────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

## 🤖 **AI Agents**

### **Text Interview Agents (Google Vertex AI)**
1. **ISA_Researcher** - Company and market research agent
   - Searches Glassdoor, Reddit, LinkedIn for interview insights
   - Identifies company-specific interview styles and questions
   - Provides market intelligence for interview preparation

2. **ISA_Detector** - Skills and competency analysis agent
   - Analyzes job descriptions for required skills
   - Identifies 5-7 key competencies for assessment
   - Creates evaluation scorecard for candidate assessment

3. **ISA_Questioner** - Dynamic question generation agent
   - Generates 10 tailored interview questions
   - Combines job requirements, resume analysis, and market research
   - Adapts questions based on company culture and role requirements

4. **ISA_Evaluator** - Interview assessment and feedback agent
   - Provides job matching feedback based on detected skills
   - Assesses interviewing skills (communication, confidence, etc.)
   - Generates comprehensive feedback and improvement recommendations

### **Voice Interview Agent (OpenAI Realtime API)**
5. **ISA_Prep_Voice** - Real-time voice interview agent
   - Conducts voice-to-voice interviews using the same question set
   - Provides natural conversation flow and real-time responses
   - Integrates with text agents for consistent evaluation criteria

## 📊 **Data Flow**

### **Interview Process**
1. **User Authentication** - URL parameter (user_id) maps to Salesforce Contact
2. **Job Analysis** - ISA_Detector analyzes job description and requirements
3. **Market Research** - ISA_Researcher gathers company-specific intelligence
4. **Question Generation** - ISA_Questioner creates 10 tailored questions
5. **Interview Execution** - User chooses text or voice interview mode
6. **Assessment** - ISA_Evaluator provides comprehensive feedback
7. **Data Storage** - All results stored in Salesforce THEIA_Interview__c object

### **Salesforce Integration**
- **User Data**: Contact object with Resume_TXT field
- **Interview Records**: THEIA_Interview__c custom object
- **Comprehensive Logging**: All interactions and assessments recorded

## 🚀 **Technology Stack**

### **Backend**
- **FastAPI** - Modern Python web framework
- **Google Vertex AI SDK** - Text-based AI agents
- **OpenAI Realtime API** - Voice interview capabilities
- **Celery** - Background task processing
- **Redis** - Session management and task queue
- **WebSocket** - Real-time communication

### **Frontend**
- **React** - Modern UI framework
- **TypeScript** - Type-safe JavaScript
- **WebRTC** - Real-time voice communication
- **WebSocket** - Real-time text communication

### **External Services**
- **Salesforce** - CRM and data storage
- **Google Cloud Vertex AI** - AI model hosting
- **OpenAI** - Realtime voice AI capabilities

## 🔒 **Compliance & Security**

- **SOC2 Compliant** architecture and logging
- **Comprehensive audit trails** for all API calls and data access
- **Secure credential management** with environment variables
- **Data encryption** in transit and at rest
- **Session timeout** and cleanup mechanisms

## 📈 **Scalability**

Designed to handle:
- **400 interviews per day**
- **20-50 concurrent interviews** during peak times
- **Horizontal scaling** with Redis-based session management
- **Load balancing** across multiple backend instances

## 🛠️ **Development Setup**

### Prerequisites
- Python 3.11+
- Node.js 16+
- Redis
- Google Cloud Account with Vertex AI enabled
- OpenAI API access with Realtime API
- Salesforce Developer Account

### Quick Start
```bash
# Backend setup
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend setup
cd frontend
npm install
npm start
```

## 📝 **Project Status**

This is a new implementation building upon the proven architecture of the ISA Interviewer system, specifically designed for interview preparation and mock interview scenarios.

### **Current Phase**: Development
- ✅ Architecture design complete
- 🔄 Project structure setup
- ⏳ Agent implementation in progress
- ⏳ Integration testing pending
- ⏳ Production deployment pending

## 📚 **Documentation**

- [Backend Documentation](./backend/README.md)
- [Frontend Documentation](./frontend/README.md)
- [API Documentation](./docs/api.md)
- [Deployment Guide](./docs/deployment.md)

---

*THEIA Interview Prep System - Empowering job seekers through AI-powered interview preparation*


