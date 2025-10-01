/**
 * THEIA Interview Prep Service
 * Handles communication with the THEIA backend API
 */

import { loadApiBase } from './apiBase';

export interface InterviewRequest {
  user_id: string;
  company_name: string;
  job_description: string;
  job_title?: string;
  interview_mode: 'text' | 'voice';
}

export interface InterviewResponse {
  session_id: string;
  status: string;
  message: string;
  interview_mode: string;
  next_step: string;
}

export interface CredentialStatus {
  timestamp: string;
  services: {
    google_cloud: {
      status: string;
      project_id?: string;
      model?: string;
      error?: string;
    };
    openai: {
      status: string;
      model?: string;
      error?: string;
    };
    salesforce: {
      status: string;
      domain?: string;
      theia_object?: string;
      error?: string;
    };
    redis: {
      status: string;
      url?: string;
      error?: string;
    };
  };
}

class TheiaService {
  private baseUrl: string = '';

  constructor() {
    // Initialize with basic logic - will be properly resolved when needed
    this.baseUrl = process.env.REACT_APP_API_URL || 
                   (window.location.hostname === 'localhost' ? 'http://localhost:8000' : '');
    
    console.log('🔧 THEIA Service initialized with initial baseUrl:', this.baseUrl);
  }

  /**
   * Resolve API base URL using the same logic as HTML files
   */
  private async resolveApiBase(): Promise<string> {
    if (this.baseUrl && this.baseUrl.startsWith('http')) return this.baseUrl;
    this.baseUrl = await loadApiBase();
    return this.baseUrl;
  }

  /**
   * Test backend connectivity and credential status
   */
  async testCredentials(): Promise<CredentialStatus> {
    const baseUrl = await this.resolveApiBase();
    const response = await fetch(`${baseUrl}/test/credentials`);
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    return response.json();
  }

  /**
   * Test agent availability
   */
  async testAgents(): Promise<any> {
    const baseUrl = await this.resolveApiBase();
    const response = await fetch(`${baseUrl}/test/agents`);
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    return response.json();
  }

  /**
   * Start an interview session
   */
  async startInterview(request: InterviewRequest): Promise<InterviewResponse> {
    const baseUrl = await this.resolveApiBase();
    const response = await fetch(`${baseUrl}/api/v1/interviews/start`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Get interview session status
   */
  async getInterviewStatus(sessionId: string): Promise<any> {
    const baseUrl = await this.resolveApiBase();
    const response = await fetch(`${baseUrl}/api/v1/interviews/${sessionId}/status`);
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    return response.json();
  }

  /**
   * Submit an answer during interview
   */
  async submitAnswer(sessionId: string, answer: string): Promise<any> {
    const baseUrl = await this.resolveApiBase();
    const response = await fetch(`${baseUrl}/api/v1/interviews/${sessionId}/answer`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message: answer }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Get interview results
   */
  async getInterviewResults(sessionId: string): Promise<any> {
    const baseUrl = await this.resolveApiBase();
    const response = await fetch(`${baseUrl}/api/v1/interviews/${sessionId}/results`);
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    return response.json();
  }

  // WebSocket functionality is deprecated/disabled in current backend

  /**
   * Generate a unique client ID
   */
  generateClientId(): string {
    return `client_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Check backend health
   */
  async checkHealth(): Promise<any> {
    const baseUrl = await this.resolveApiBase();
    const response = await fetch(`${baseUrl}/health`);
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    return response.json();
  }
}

// Export singleton instance
export const theiaService = new TheiaService();
export default theiaService;


