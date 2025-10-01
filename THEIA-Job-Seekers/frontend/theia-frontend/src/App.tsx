import React, { useState, useEffect } from 'react';
import theiaService, { InterviewRequest } from './services/theiaService';

interface InterviewFormData {
  companyName: string;
  jobDescription: string;
  jobTitle: string;
  interviewMode: 'text' | 'voice';
}

const App: React.FC = () => {
  const [formData, setFormData] = useState<InterviewFormData>({
    companyName: '',
    jobDescription: '',
    jobTitle: '',
    interviewMode: 'text'
  });

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [backendStatus, setBackendStatus] = useState<string>('checking');

  // Check backend status on component mount
  useEffect(() => {
    checkBackendStatus();
  }, []);

  const checkBackendStatus = async () => {
    try {
      await theiaService.checkHealth();
      const credentials = await theiaService.testCredentials();
      
      // Check if all services are working
      const allWorking = Object.values(credentials.services).every(
        service => service.status.includes('WORKING')
      );
      
      setBackendStatus(allWorking ? 'ready' : 'partial');
    } catch (error) {
      setBackendStatus('error');
      console.error('Backend status check failed:', error);
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      const interviewRequest: InterviewRequest = {
        user_id: 'demo_user_123', // TODO: Get from URL parameter or auth
        company_name: formData.companyName,
        job_description: formData.jobDescription,
        job_title: formData.jobTitle,
        interview_mode: formData.interviewMode
      };

      console.log('Starting THEIA interview:', interviewRequest);
      
      // Send to THEIA backend
      const response = await theiaService.startInterview(interviewRequest);
      console.log('THEIA Response:', response);
      
      setSubmitted(true);
    } catch (error) {
      console.error('Error starting interview:', error);
      alert('Error starting interview. Please check the backend is running.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const isFormValid = formData.companyName.trim() && formData.jobDescription.trim();

  if (submitted) {
    return (
      <>
        <header className="site-header">
          <div className="site-header__inner">
            <img src="/THEIA-logo.png" alt="THEIA logo" className="brand-logo" />
            <div className="brand-center">
              <div className="brand__title">THEIA</div>
              <div className="brand__subtitle">Show your value. Get the job</div>
            </div>
            <img src="/user-icon.svg" alt="User avatar" className="avatar" />
          </div>
        </header>
        <div className="container">
          <div className="success-message">
            <h1>🎉 Interview Preparation Started!</h1>
            <p>THEIA is analyzing the job requirements and preparing your personalized interview...</p>
            <div className="interview-details">
              <h3>Interview Details:</h3>
              <p><strong>Company:</strong> {formData.companyName}</p>
              <p><strong>Job Title:</strong> {formData.jobTitle || 'Not specified'}</p>
              <p><strong>Mode:</strong> {formData.interviewMode === 'voice' ? '🎤 Voice Interview' : '💬 Text Interview'}</p>
            </div>
            <div className="next-steps">
              <h3>What's happening now:</h3>
              <ul>
                <li>✅ Researching {formData.companyName} interview practices</li>
                <li>🔍 Analyzing job requirements and key skills</li>
                <li>❓ Generating personalized interview questions</li>
                <li>🎯 Preparing evaluation criteria</li>
              </ul>
            </div>
            <button 
              onClick={() => setSubmitted(false)}
              className="btn"
            >
              Start Another Interview
            </button>
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <header className="site-header">
        <div className="site-header__inner">
          <img src="/THEIA-logo.png" alt="THEIA logo" className="brand-logo" />
          <div className="brand-center">
            <div className="brand__title">THEIA</div>
            <div className="brand__subtitle">Show your value. Get the job</div>
          </div>
          <img src="/user-icon.svg" alt="User avatar" className="avatar" />
        </div>
      </header>
      
      <div className="container" style={{ marginTop: 'calc(80px + var(--space-5))' }}>
        <div className="header">
          <h1>🎯 THEIA Interview Prep</h1>
          <p>AI-powered interview preparation system</p>
          
          {/* Backend Status Indicator */}
          <div className={`status-indicator status-${backendStatus}`}>
            {backendStatus === 'checking' && '🔍 Checking backend...'}
            {backendStatus === 'ready' && '✅ All systems ready'}
            {backendStatus === 'partial' && '⚠️ Some services need configuration'}
            {backendStatus === 'error' && '❌ Backend not available'}
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="form-section">
            <h2>📋 Interview Setup</h2>
            <p>Enter the job details to start your personalized interview preparation</p>
          </div>

          <div className="form-group">
            <label htmlFor="companyName">
              🏢 Company Name *
            </label>
            <input
              type="text"
              id="companyName"
              name="companyName"
              value={formData.companyName}
              onChange={handleInputChange}
              placeholder="e.g., Google, Microsoft, Apple..."
              required
              className="form-input"
            />
          </div>

          <div className="form-group">
            <label htmlFor="jobTitle">
              💼 Job Title (Optional)
            </label>
            <input
              type="text"
              id="jobTitle"
              name="jobTitle"
              value={formData.jobTitle}
              onChange={handleInputChange}
              placeholder="e.g., Software Engineer, Product Manager..."
              className="form-input"
            />
          </div>

          <div className="form-group">
            <label htmlFor="jobDescription">
              📝 Full Job Description *
            </label>
            <textarea
              id="jobDescription"
              name="jobDescription"
              value={formData.jobDescription}
              onChange={handleInputChange}
              placeholder="Paste the complete job description here including requirements, responsibilities, and qualifications..."
              required
              className="form-textarea"
              rows={12}
            />
            <small>
              💡 Include the full job posting for better question generation
            </small>
          </div>

          <div className="form-group">
            <label htmlFor="interviewMode">
              🎙️ Interview Mode
            </label>
            <select
              id="interviewMode"
              name="interviewMode"
              value={formData.interviewMode}
              onChange={handleInputChange}
              className="form-select"
            >
              <option value="text">💬 Text Interview (Chat-based)</option>
              <option value="voice">🎤 Voice Interview (Real-time voice)</option>
            </select>
            <small>
              Choose how you'd like to practice your interview
            </small>
          </div>

          <div className="form-actions">
            <button
              type="submit"
              disabled={!isFormValid || isSubmitting}
              className="btn"
            >
              {isSubmitting ? (
                <>
                  <span className="spinner"></span>
                  Preparing Interview...
                </>
              ) : (
                '🚀 Start Interview Preparation'
              )}
            </button>
          </div>
        </form>

        <div className="info-section">
          <h3><img src="/isa_portrait.png" alt="ISA" style={{ width: 24, height: 24, borderRadius: '50%', verticalAlign: 'middle', marginRight: 8 }} /> What THEIA Will Do:</h3>
          <div className="info-grid">
            <div className="info-item">
              <strong>🔍 Research</strong>
              <p>Analyze company culture and interview practices</p>
            </div>
            <div className="info-item">
              <strong>🎯 Skills Analysis</strong>
              <p>Identify 5-7 key skills required for success</p>
            </div>
            <div className="info-item">
              <strong>❓ Question Generation</strong>
              <p>Create 10 tailored interview questions</p>
            </div>
            <div className="info-item">
              <strong>📊 Evaluation</strong>
              <p>Provide comprehensive feedback and scoring</p>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

export default App;